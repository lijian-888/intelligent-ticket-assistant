from fastapi.testclient import TestClient
import pytest

from app.api import create_app
from app.db import get_connection, init_db
from app.embedding_client import embed_texts, get_embedding_config_status, get_embedding_runtime_model
from app.models import CaseNature, ProcessingResult, StructuredTicket, Ticket, TicketStatus
from app.nodes import analyze_emotion, assess_professional_claimant, classify_case_nature, classify_case_nature_detail
from app.reranker_client import _parse_rerank_response
from app.supplement import build_supplement_task


client = TestClient(create_app())


@pytest.fixture(autouse=True)
def disable_real_llm_calls(monkeypatch, tmp_path):
    """测试默认不访问真实大模型接口，避免外部网络影响测试稳定性。"""

    def fake_call_llm_json(messages, **kwargs):
        content = messages[-1]["content"]
        if "should_return" in content:
            return {
                "should_return": False,
                "confidence": 0.8,
                "reason": "无明显不予受理情形",
                "rule_category": "无",
                "handling_suggestion": "继续后续处理",
            }
        if "inferred_fields" in content:
            return {"inferred_fields": []}
        return {
            "case_nature_review": "无法判断",
            "confidence": 0.8,
            "case_nature_reason_review": "测试中禁用真实 LLM 调用。",
            "handling_summary": "测试摘要",
            "mediation_advice_review": "测试建议",
            "risk_notes": [],
            "return_reason_review": "",
        }

    monkeypatch.setattr("app.db.DB_PATH", tmp_path / "test_demo.db")
    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM supplement_tasks")
    monkeypatch.setattr("app.nodes.is_llm_configured", lambda: False)
    monkeypatch.setattr("app.nodes.call_llm_json", fake_call_llm_json)


def test_list_tickets_returns_mock_data():
    """工单列表接口应返回当前 demo 的 mock 工单。"""

    response = client.get("/tickets")

    assert response.status_code == 200
    assert len(response.json()) == 10


def test_process_one_classifies_complaint():
    """单工单处理接口应返回投诉/举报分类和动作建议。"""

    response = client.post("/tickets/DEMO-TICKET-001/process")
    body = response.json()

    assert response.status_code == 200
    assert body["structured"]["case_nature"] == "投诉"
    assert body["status"] == "待流转"
    assert body["recommended_branch"] == "北京市朝阳区市场监督管理部门建国路承办单位"
    assert body["actions"][0]["tool"] == "transfer_ticket"


def test_process_one_returns_related_legal_references():
    """法律条款混合检索应返回通过阈值过滤后的少量候选。"""

    response = client.post("/tickets/DEMO-TICKET-001/process")
    body = response.json()
    law_names = [item["law_name"] for item in body["legal_references"]]

    assert response.status_code == 200
    assert body["legal_references"]
    assert "中华人民共和国消费者权益保护法" in law_names
    assert len(body["legal_references"]) <= 3
    assert all(item["retrieval_method"] in {"vector", "hybrid_vector_rerank"} for item in body["legal_references"])
    assert all(item["embedding_model"] for item in body["legal_references"])
    assert all(item["source_id"] for item in body["legal_references"])
    assert all(item["relevance_score"] >= 0.55 for item in body["legal_references"])


def test_smart_transfer_low_confidence_keeps_manual_recommendation():
    """置信度不足时，智能流转只给出推荐动作，不自动执行接口。"""

    response = client.post("/tickets/DEMO-TICKET-001/smart-transfer")
    body = response.json()

    assert response.status_code == 200
    assert body["automation_mode"] == "manual_review"
    assert body["actions"][0]["executed"] is False


def test_smart_transfer_high_confidence_auto_executes_transfer(monkeypatch):
    """置信度高时，智能流转应自动模拟调用对应流转接口。"""

    def fake_call_llm_json(messages, **kwargs):
        content = messages[-1]["content"]
        if "should_return" in content:
            return {
                "should_return": False,
                "confidence": 0.95,
                "reason": "无不予受理情形",
                "rule_category": "无",
                "handling_suggestion": "继续流转",
            }
        if "case_nature" in content:
            return {"case_nature": "投诉", "confidence": 0.95, "reason": "模型识别为投诉"}
        return {
            "case_nature_review": "投诉",
            "confidence": 0.95,
            "case_nature_reason_review": "整体复核通过",
            "handling_summary": "可流转",
            "mediation_advice_review": "正常处理",
            "risk_notes": [],
            "return_reason_review": "",
        }

    monkeypatch.setattr("app.nodes.is_llm_configured", lambda: True)
    monkeypatch.setattr("app.nodes.LLM_ENABLE_REVIEW", True)
    monkeypatch.setattr("app.nodes.call_llm_json", fake_call_llm_json)

    response = client.post("/tickets/DEMO-TICKET-001/smart-transfer")
    body = response.json()

    assert response.status_code == 200
    assert body["automation_mode"] == "auto_executed"
    assert body["automation_confidence"] >= 0.85
    assert body["actions"][0]["tool"] == "transfer_ticket"
    assert body["actions"][0]["executed"] is True


def test_smart_transfer_return_requires_manual_review_even_when_confidence_is_high(monkeypatch):
    """退单必须人工确认，即使 LLM 退单置信度很高也不能自动退单。"""

    def fake_call_llm_json(messages, **kwargs):
        content = messages[-1]["content"]
        if "should_return" in content:
            return {
                "should_return": True,
                "confidence": 0.95,
                "reason": "未提供联系电话、事发地址等核心信息，无法明确处理。",
                "rule_category": "材料不足",
                "handling_suggestion": "补充信息后继续处理",
            }
        if "case_nature" in content:
            return {"case_nature": "投诉", "confidence": 0.95, "reason": "模型识别为投诉"}
        return {
            "case_nature_review": "投诉",
            "confidence": 0.95,
            "case_nature_reason_review": "整体复核通过",
            "handling_summary": "需补充",
            "mediation_advice_review": "正常处理",
            "risk_notes": [],
            "return_reason_review": "",
        }

    monkeypatch.setattr("app.nodes.is_llm_configured", lambda: True)
    monkeypatch.setattr("app.nodes.call_llm_json", fake_call_llm_json)

    response = client.post("/tickets/DEMO-TICKET-006/smart-transfer")
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "建议退单"
    assert body["automation_mode"] == "manual_review"
    assert body["actions"][0]["tool"] == "return_ticket"
    assert body["actions"][0]["executed"] is False
    assert "未提供" in body["return_reason"]


def test_smart_transfer_return_below_return_threshold_requires_manual_review(monkeypatch):
    """退单不再自动执行，低置信度同样只能推荐人工确认。"""

    def fake_call_llm_json(messages, **kwargs):
        content = messages[-1]["content"]
        if "should_return" in content:
            return {
                "should_return": True,
                "confidence": 0.85,
                "reason": "不属于市场监管职责。",
                "rule_category": "不属于市场监管职责",
                "handling_suggestion": "建议退单",
            }
        if "case_nature" in content:
            return {"case_nature": "投诉", "confidence": 0.95, "reason": "模型识别为投诉"}
        return {
            "case_nature_review": "投诉",
            "confidence": 0.95,
            "case_nature_reason_review": "整体复核通过",
            "handling_summary": "建议退单",
            "mediation_advice_review": "正常处理",
            "risk_notes": [],
            "return_reason_review": "",
        }

    monkeypatch.setattr("app.nodes.is_llm_configured", lambda: True)
    monkeypatch.setattr("app.nodes.call_llm_json", fake_call_llm_json)

    response = client.post("/tickets/DEMO-TICKET-006/smart-transfer")
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "建议退单"
    assert body["automation_confidence"] == 0.85
    assert body["automation_mode"] == "manual_review"
    assert body["actions"][0]["executed"] is False


def test_process_all_contains_return_recommendation():
    """批量处理结果应覆盖建议退单样例。"""

    response = client.post("/process-all")
    body = response.json()

    assert response.status_code == 200
    assert any(item["status"] == "建议退单" for item in body)


def test_ambiguous_ticket_can_be_unknown_case_nature():
    """模糊咨询样例：信息过少时可能无法判断投诉/举报，应提示人工复核。"""

    response = client.post("/tickets/DEMO-TICKET-007/process")
    body = response.json()

    assert response.status_code == 200
    assert body["structured"]["case_nature"] == "无法判断"
    assert body["status"] == "建议退单"
    assert "人工复核" in body["return_reason"]


def test_non_national_region_cannot_recommend_branch():
    """全国不同地区样例：当前 demo 只处理北京市朝阳区工单，不能推荐建议承办单位。"""

    response = client.post("/tickets/DEMO-TICKET-008/process")
    body = response.json()

    assert response.status_code == 200
    assert body["recommended_branch"] == ""
    assert body["jurisdiction"] == "市场监管职责范围"
    assert body["status"] == "建议退单"


def test_report_with_insufficient_object_and_address_needs_review():
    """举报缺少对象、链接、地址或证据时，应进入补充核心字段流程。"""

    response = client.post("/tickets/DEMO-TICKET-009/process")
    body = response.json()

    assert response.status_code == 200
    assert body["structured"]["case_nature"] == "举报"
    assert "事发地址" in body["missing_fields"]
    assert body["status"] == "待补充"
    assert body["return_reason"] == ""


def test_property_fee_ticket_recommends_return():
    """职责边界样例：物业收费纠纷通常不属于市场监管主责，建议退单或转办。"""

    response = client.post("/tickets/DEMO-TICKET-010/process")
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "建议退单"
    assert "物业" in body["return_reason"]


def test_process_steps_returns_langgraph_nodes():
    """过程接口应返回 LangGraph 每个处理节点的中间输出。"""

    response = client.post("/tickets/DEMO-TICKET-001/process/steps")
    body = response.json()
    nodes = [item["node"] for item in body]

    assert response.status_code == 200
    assert "structure_ticket" in nodes
    assert "retrieve_legal_references" in nodes
    assert "infer_missing_required_fields" in nodes
    assert "decide_action" in nodes
    assert "build_result" in nodes
    assert body[-1]["node"] == "__total__"
    assert body[-1]["duration_ms"] >= 0
    assert any(item["node"] == "structure_ticket" and item["duration_ms"] is not None for item in body)


def test_incomplete_ticket_reports_missing_fields():
    """信息不完整工单应进入待补充，并列出缺失字段。"""

    response = client.post("/tickets/DEMO-TICKET-006/process")
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "待补充"
    assert "联系电话" in body["missing_fields"]
    assert "事发地址" in body["missing_fields"]
    assert "所属区域" in body["missing_fields"]
    assert "被投诉/举报对象" in body["recommended_supplement_fields"]
    assert "事发时间" in body["recommended_supplement_fields"]


def test_create_supplement_task_for_incomplete_ticket():
    """缺失核心字段的工单应能生成电话补充任务。"""

    response = client.post("/tickets/DEMO-TICKET-006/supplement-task")
    body = response.json()

    assert response.status_code == 200
    assert body["ticket_no"] == "DEMO-TICKET-006"
    assert body["priority"] == "普通"
    assert "联系电话" in body["missing_fields"]
    assert "被投诉/举报对象" in body["recommended_supplement_fields"]
    assert "请联系提交人核实并补充" in body["call_script"]


def test_complete_ticket_does_not_create_supplement_task():
    """完整工单不应生成补充任务。"""

    response = client.post("/tickets/DEMO-TICKET-001/supplement-task")

    assert response.status_code == 400


def test_supplement_task_depends_on_missing_fields_not_final_status():
    """只要存在核心字段缺失，即使最终动作不是待补充，也应允许生成补充任务。"""

    process_response = client.post("/tickets/DEMO-TICKET-006/process")
    result = ProcessingResult.model_validate(process_response.json())
    result.status = TicketStatus.RETURN_RECOMMENDED

    task = build_supplement_task(Ticket.model_validate(client.get("/tickets/DEMO-TICKET-006").json()), result)

    assert task is not None
    assert task.source_status == TicketStatus.NEED_SUPPLEMENT
    assert "联系电话" in task.missing_fields


def test_list_supplement_tasks():
    """补充任务列表应包含所有待补充工单。"""

    client.post("/tickets/DEMO-TICKET-006/supplement-task")
    response = client.get("/supplement-tasks")
    body = response.json()

    assert response.status_code == 200
    assert any(item["ticket_no"] == "DEMO-TICKET-006" for item in body)


def test_unknown_ticket_returns_404():
    """不存在的工单编号应返回 404。"""

    response = client.get("/tickets/not-exists")

    assert response.status_code == 404


def test_llm_config_endpoint_is_masked():
    """LLM 配置接口应返回脱敏状态，不暴露 API key。"""

    response = client.get("/llm/config")
    body = response.json()

    assert response.status_code == 200
    assert "api_key_set" in body
    assert "api_key" not in body


def test_embedding_config_endpoint_is_masked():
    """向量模型配置接口应返回脱敏状态，不暴露 embedding API key。"""

    response = client.get("/embedding/config")
    body = response.json()

    assert response.status_code == 200
    assert body["model"] == "bge-m3"
    assert "api_key_set" in body
    assert "api_key" not in body


def test_retrieval_config_endpoint_contains_reranker_settings():
    """混合检索配置接口应包含法律检索、embedding 和 reranker 脱敏配置。"""

    response = client.get("/retrieval/config")
    body = response.json()

    assert response.status_code == 200
    assert body["legal_retrieval"]["display_top_k"] == 3
    assert "embedding" in body
    assert "reranker" in body
    assert "api_key" not in body["reranker"]


def test_embedding_remote_failure_falls_back_to_local_vector(monkeypatch):
    """bge-m3 服务异常时，向量生成应降级到本地 demo 向量，避免工单处理接口中断。"""

    monkeypatch.setattr("app.embedding_client.EMBEDDING_BASE_URL", "http://embedding.local")

    def fake_remote_call(texts):
        raise TimeoutError("embedding timeout")

    monkeypatch.setattr("app.embedding_client._embed_texts_remote", fake_remote_call)

    vectors = embed_texts(["虚假宣传要求赔偿"])
    status = get_embedding_config_status()

    assert len(vectors) == 1
    assert get_embedding_runtime_model() == "local-demo-vector"
    assert status["last_embedding_source"] == "fallback"
    assert "TimeoutError" in status["last_error"]


def test_reranker_response_scores_are_normalized():
    """reranker 原始 logit 分数应归一化为 0-1，便于按阈值过滤。"""

    results = _parse_rerank_response(
        {
            "results": [
                {"index": 0, "relevance_score": -2.0},
                {"index": 1, "relevance_score": 2.0},
            ]
        }
    )

    assert 0 < results[0].score < 0.5
    assert 0.5 < results[1].score < 1


def test_classify_case_nature_uses_llm_when_configured(monkeypatch):
    """配置了 LLM 时，投诉/举报分类应优先采用模型返回结果。"""

    def fake_call_llm_json(messages, **kwargs):
        return {"case_nature": "举报", "confidence": 0.91, "reason": "模型识别为违法查处诉求"}

    monkeypatch.setattr("app.nodes.is_llm_configured", lambda: True)
    monkeypatch.setattr("app.nodes.call_llm_json", fake_call_llm_json)

    ticket = Ticket(
        ticket_no="TEST001",
        title="要求退款赔偿",
        content="消费者购买商品后要求退款赔偿。",
    )

    nature, reason = classify_case_nature(ticket)

    assert nature == CaseNature.REPORT
    assert reason.startswith("LLM识别")


def test_low_confidence_llm_classification_falls_back_to_rule(monkeypatch):
    """LLM 置信度低于阈值时不能采纳，应回退规则分类。"""

    monkeypatch.setattr("app.nodes.is_llm_configured", lambda: True)
    monkeypatch.setattr(
        "app.nodes.call_llm_json",
        lambda messages, **kwargs: {"case_nature": "举报", "confidence": 0.2, "reason": "低置信度判断"},
    )

    ticket = Ticket(
        ticket_no="TEST002",
        title="要求退款赔偿",
        content="消费者购买商品后要求退款赔偿。",
    )

    detail = classify_case_nature_detail(ticket)

    assert detail["case_nature"] == CaseNature.COMPLAINT
    assert detail["source"] == "rule_fallback"
    assert detail["llm_result"]["audit"]["accepted"] is False
    assert "低于阈值" in detail["llm_result"]["error"]


def test_invalid_llm_classification_schema_falls_back_to_rule(monkeypatch):
    """LLM 输出不符合 schema 时不能采纳，应回退规则分类。"""

    monkeypatch.setattr("app.nodes.is_llm_configured", lambda: True)
    monkeypatch.setattr("app.nodes.call_llm_json", lambda messages, **kwargs: {"case_nature": "其他", "reason": "非法枚举"})

    ticket = Ticket(
        ticket_no="TEST003",
        title="举报过期食品",
        content="发现便利店销售过期食品，要求依法查处。",
    )

    detail = classify_case_nature_detail(ticket)

    assert detail["case_nature"] == CaseNature.REPORT
    assert detail["source"] == "rule_fallback"
    assert "schema 校验失败" in detail["llm_result"]["error"]


def test_llm_can_infer_missing_required_fields(monkeypatch):
    """阻断字段缺失时，LLM 高置信度推断结果可用于通过完整性校验。"""

    def fake_call_llm_json(messages, **kwargs):
        content = messages[-1]["content"]
        if "inferred_fields" in content:
            return {
                "inferred_fields": [
                    {"field": "contact_phone", "value": "demo-phone-from-text", "confidence": 0.9, "reason": "正文提及手机号"},
                    {"field": "incident_address", "value": "北京市北京市朝阳区", "confidence": 0.9, "reason": "正文提及地址"},
                    {"field": "region", "value": "北京市朝阳区", "confidence": 0.9, "reason": "由地址归纳"},
                ]
            }
        return {
            "case_nature_review": "投诉",
            "confidence": 0.8,
            "case_nature_reason_review": "测试复核",
            "handling_summary": "测试摘要",
            "mediation_advice_review": "测试建议",
            "risk_notes": [],
            "return_reason_review": "",
        }

    monkeypatch.setattr("app.nodes.is_llm_configured", lambda: True)
    monkeypatch.setattr("app.nodes.call_llm_json", fake_call_llm_json)

    response = client.post("/tickets/DEMO-TICKET-006/process")
    body = response.json()

    assert response.status_code == 200
    assert body["missing_fields"] == []
    assert body["inferred_required_fields"]["audit"]["accepted"] is True


def test_low_confidence_inferred_required_fields_are_not_used(monkeypatch):
    """阻断字段推断置信度低时不能用于补齐，仍应进入待补充。"""

    def fake_call_llm_json(messages, **kwargs):
        content = messages[-1]["content"]
        if "inferred_fields" in content:
            return {
                "inferred_fields": [
                    {"field": "contact_phone", "value": "demo-phone-from-text", "confidence": 0.2, "reason": "不确定"}
                ]
            }
        return {
            "case_nature_review": "投诉",
            "confidence": 0.8,
            "case_nature_reason_review": "测试复核",
            "handling_summary": "测试摘要",
            "mediation_advice_review": "测试建议",
            "risk_notes": [],
            "return_reason_review": "",
        }

    monkeypatch.setattr("app.nodes.is_llm_configured", lambda: True)
    monkeypatch.setattr("app.nodes.call_llm_json", fake_call_llm_json)

    response = client.post("/tickets/DEMO-TICKET-006/process")
    body = response.json()

    assert response.status_code == 200
    assert "联系电话" in body["missing_fields"]
    assert body["status"] == "待补充"


def test_analyze_emotion_uses_llm_when_configured(monkeypatch):
    """配置了 LLM 时，情绪等级应优先采用模型返回结果。"""

    monkeypatch.setattr("app.nodes.is_llm_configured", lambda: True)
    monkeypatch.setattr(
        "app.nodes.call_llm_json",
        lambda messages, **kwargs: {
            "emotion_level": "高",
            "confidence": 0.92,
            "reason": "模型识别到强烈施压表达。",
            "mediation_advice": "建议优先回访并明确办理时限。",
        },
    )

    result = analyze_emotion(
        {
            "ticket": Ticket(
                ticket_no="TEST_EMOTION",
                title="要求马上处理",
                content="提交人表示如果不处理就继续投诉。",
            )
        }
    )

    assert result["emotion_level"] == "高"
    assert result["mediation_advice"] == "建议优先回访并明确办理时限。"
    assert result["emotion_analysis"]["audit"]["accepted"] is True


def test_professional_claimant_uses_llm_when_configured(monkeypatch):
    """配置了 LLM 时，职业索赔风险应优先采用模型返回结果。"""

    monkeypatch.setattr("app.nodes.is_llm_configured", lambda: True)
    monkeypatch.setattr(
        "app.nodes.call_llm_json",
        lambda messages, **kwargs: {
            "professional_claimant_risk": "中",
            "confidence": 0.9,
            "reasons": ["模型识别到惩罚性赔偿和专业法条表述，但缺少历史数据。"],
        },
    )
    ticket = Ticket(
        ticket_no="TEST_RISK",
        title="要求十倍赔偿",
        content="依据食品安全法第一百四十八条要求十倍赔偿。",
        appeal_purpose="十倍赔偿",
    )
    structured = StructuredTicket(
        ticket_no=ticket.ticket_no,
        title=ticket.title,
        raw_content=ticket.content,
        case_nature=CaseNature.COMPLAINT,
        case_nature_reason="测试",
        complainant_name="",
        contact_phone="",
        incident_address="",
        region="",
        respondent="",
        appeal="十倍赔偿",
        incident_at="",
        amount=20,
        keywords=["十倍赔偿"],
    )

    result = assess_professional_claimant({"ticket": ticket, "structured": structured})

    assert result["professional_claimant_risk"] == "中"
    assert result["professional_claimant_reasons"] == ["模型识别到惩罚性赔偿和专业法条表述，但缺少历史数据。"]
    assert result["professional_claimant_llm_result"]["audit"]["accepted"] is True


def test_professional_claimant_high_risk_explains_score():
    """职业索赔风险识别应输出评分和可解释原因。"""

    response = client.post("/tickets/DEMO-TICKET-005/process")
    body = response.json()

    assert response.status_code == 200
    assert body["professional_claimant_risk"] == "高"
    assert any("风险评分" in reason for reason in body["professional_claimant_reasons"])
    assert any("十倍赔偿" in reason for reason in body["professional_claimant_reasons"])


def test_no_history_data_does_not_force_high_risk():
    """没有历史数据时，只能基于单条工单文本提示风险，不能直接判高风险。"""

    response = client.post("/tickets/DEMO-TICKET-001/process")
    body = response.json()

    assert response.status_code == 200
    assert body["professional_claimant_risk"] in {"低", "中"}
    assert any("未提供历史投诉数据" in reason for reason in body["professional_claimant_reasons"])


def test_high_risk_professional_claimant_does_not_change_normal_handling(monkeypatch):
    """职业索赔高风险只做预警，不应单独改变补充、流转或退单流程。"""

    def fake_call_llm_json(messages, **kwargs):
        if "should_return" in messages[-1]["content"]:
            return {
                "should_return": False,
                "confidence": 0.92,
                "reason": "职业索赔风险仅作为工作人员关注提醒，工单本身仍按普通投诉处理。",
                "rule_category": "无",
                "handling_suggestion": "继续后续核心字段校验和属地分派。",
            }
        if "case_nature" in messages[-1]["content"]:
            return {"case_nature": "投诉", "confidence": 0.95, "reason": "模型识别为投诉"}
        return {
            "case_nature_review": "投诉",
            "confidence": 0.8,
            "case_nature_reason_review": "测试复核",
            "handling_summary": "测试摘要",
            "mediation_advice_review": "测试建议",
            "risk_notes": [],
            "return_reason_review": "",
        }

    monkeypatch.setattr("app.nodes.is_llm_configured", lambda: True)
    monkeypatch.setattr("app.nodes.call_llm_json", fake_call_llm_json)

    response = client.post("/tickets/DEMO-TICKET-005/process")
    body = response.json()

    assert response.status_code == 200
    assert body["professional_claimant_risk"] == "高"
    assert body["status"] == "待补充"
    assert "事发地址" in body["missing_fields"]
    assert body["return_reason"] == ""


def test_report_with_professional_claimant_risk_is_not_returned_by_profit_rule(monkeypatch):
    """同样高风险文本若被识别为举报，不能因知假买假投诉规则直接退单。"""

    def fake_call_llm_json(messages, **kwargs):
        if "should_return" in messages[-1]["content"]:
            return {
                "should_return": False,
                "confidence": 0.91,
                "reason": "虽存在职业索赔风险，但举报部分包含经营者违法线索，应继续处理。",
                "rule_category": "无",
                "handling_suggestion": "继续后续举报处理。",
            }
        if "case_nature" in messages[-1]["content"]:
            return {"case_nature": "举报", "confidence": 0.95, "reason": "模型识别为举报违法线索"}
        return {
            "case_nature_review": "举报",
            "confidence": 0.8,
            "case_nature_reason_review": "测试复核",
            "handling_summary": "测试摘要",
            "mediation_advice_review": "测试建议",
            "risk_notes": [],
            "return_reason_review": "",
        }

    monkeypatch.setattr("app.nodes.is_llm_configured", lambda: True)
    monkeypatch.setattr("app.nodes.call_llm_json", fake_call_llm_json)

    response = client.post("/tickets/DEMO-TICKET-005/process")
    body = response.json()

    assert response.status_code == 200
    assert body["structured"]["case_nature"] == "举报"
    assert "知假买假" not in body["return_reason"]


def test_acceptance_precheck_uses_llm_before_rule(monkeypatch):
    """不予受理初筛应优先采用高置信度 LLM 判断。"""

    def fake_call_llm_json(messages, **kwargs):
        content = messages[-1]["content"]
        if "should_return" in content:
            return {
                "should_return": True,
                "confidence": 0.9,
                "reason": "LLM 判断该事项不属于市场监管职责。",
                "rule_category": "不属于市场监管职责",
                "handling_suggestion": "建议退单并说明转办方向。",
            }
        if "case_nature" in content:
            return {"case_nature": "投诉", "confidence": 0.95, "reason": "模型识别为投诉"}
        return {
            "case_nature_review": "投诉",
            "confidence": 0.8,
            "case_nature_reason_review": "测试复核",
            "handling_summary": "测试摘要",
            "mediation_advice_review": "测试建议",
            "risk_notes": [],
            "return_reason_review": "",
        }

    monkeypatch.setattr("app.nodes.is_llm_configured", lambda: True)
    monkeypatch.setattr("app.nodes.call_llm_json", fake_call_llm_json)

    response = client.post("/tickets/DEMO-TICKET-001/process")
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "建议退单"
    assert body["acceptance_precheck"]["audit"]["accepted"] is True
    assert "不属于市场监管职责" in body["return_reason"]


def test_low_confidence_acceptance_precheck_falls_back_to_rule(monkeypatch):
    """不予受理初筛 LLM 低置信度时应回退规则判断。"""

    def fake_call_llm_json(messages, **kwargs):
        content = messages[-1]["content"]
        if "should_return" in content:
            return {
                "should_return": True,
                "confidence": 0.2,
                "reason": "低置信度退单判断",
                "rule_category": "不属于市场监管职责",
                "handling_suggestion": "建议退单",
            }
        if "case_nature" in content:
            return {"case_nature": "投诉", "confidence": 0.95, "reason": "模型识别为投诉"}
        return {
            "case_nature_review": "投诉",
            "confidence": 0.8,
            "case_nature_reason_review": "测试复核",
            "handling_summary": "测试摘要",
            "mediation_advice_review": "测试建议",
            "risk_notes": [],
            "return_reason_review": "",
        }

    monkeypatch.setattr("app.nodes.is_llm_configured", lambda: True)
    monkeypatch.setattr("app.nodes.call_llm_json", fake_call_llm_json)

    response = client.post("/tickets/DEMO-TICKET-001/process")
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "待流转"
    assert body["acceptance_precheck"]["audit"]["accepted"] is False
