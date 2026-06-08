from fastapi.testclient import TestClient
import pytest
from zipfile import ZipFile

from app.api import create_app
from app.db import get_connection, init_db
from app.embedding_client import embed_texts, get_embedding_config_status, get_embedding_runtime_model
from app.legal_docx_parser import _rebuild_pdf_paragraphs, parse_legal_document, parse_legal_docx
from app.models import CaseNature, ProcessingResult, StructuredTicket, Ticket, TicketStatus
from app.nodes import analyze_emotion, assess_professional_claimant, classify_case_nature, classify_case_nature_detail
from app.reranker_client import _parse_rerank_response
from app.supplement import build_supplement_task
from scripts.clean_legal_filenames import clean_legal_filename


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
    monkeypatch.setenv("LEGAL_KB_BACKEND", "mock")
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
    assert "legal_kb" in body


def test_legal_kb_status_endpoint_uses_mock_backend_in_tests():
    """测试环境应使用 mock 知识库后端，避免误连真实 PostgreSQL。"""

    response = client.get("/legal-kb/status")
    body = response.json()

    assert response.status_code == 200
    assert body["backend"] == "mock"
    assert body["configured"] is False


def test_legal_kb_preview_endpoint_returns_file_chunks(tmp_path):
    """法规切片预览接口应返回目录中文件的切片结果。"""

    docx_path = tmp_path / "测试法规.docx"
    other_docx_path = tmp_path / "其他法规.docx"
    _write_minimal_docx(
        docx_path,
        [
            "测试法规",
            "第一条　用于预览接口测试。",
            "第二条　测试分页和片段内容。",
        ],
    )
    _write_minimal_docx(
        other_docx_path,
        [
            "其他法规",
            "第一条　不应出现在测试法规搜索结果中。",
        ],
    )

    response = client.get("/legal-kb/preview", params={"path": str(tmp_path), "limit": 1, "offset": 1})
    body = response.json()

    assert response.status_code == 200
    assert body["document_count"] == 2
    assert body["chunk_count"] == 3
    assert len(body["items"]) == 1
    assert body["items"][0]["article"] in {"第一条", "第二条"}

    search_response = client.get(
        "/legal-kb/preview",
        params={"path": str(tmp_path), "source_file": "测试法规", "limit": 10},
    )
    search_body = search_response.json()

    assert search_response.status_code == 200
    assert search_body["chunk_count"] == 3
    assert search_body["filtered_chunk_count"] == 2
    assert all("测试法规" in item["source_file"] for item in search_body["items"])


def test_legal_kb_chunks_endpoint_returns_empty_when_postgres_disabled():
    """测试环境未启用 PostgreSQL 知识库时，数据库片段接口应返回空列表和状态。"""

    response = client.get("/legal-kb/chunks", params={"source_file": "黄河保护法"})
    body = response.json()

    assert response.status_code == 200
    assert body["configured"] is False
    assert body["items"] == []


def test_parse_legal_docx_splits_articles(tmp_path):
    """法规 docx 解析器应跳过目录，并按条文切分正文。"""

    docx_path = tmp_path / "测试法规.docx"
    _write_minimal_docx(
        docx_path,
        [
            "测试法规",
            "（2026年1月1日发布）",
            "目　　录",
            "第一章　总　　则",
            "第二章　法律责任",
            "第一章　总　　则",
            "第一条　为了测试知识库导入，制定本规定。",
            "第二条　市场监管部门依法处理相关事项。",
            "（一）投诉举报处理。",
            "第二章　法律责任",
            "第三条　违反本规定的，依法处理。",
        ],
    )

    document = parse_legal_docx(docx_path)

    assert document.law_name == "测试法规"
    assert len(document.chunks) == 3
    assert document.chunks[0].article == "第一条"
    assert "目录" not in document.chunks[0].chunk_text
    assert "投诉举报处理" in document.chunks[1].chunk_text


def test_clean_legal_filename_removes_number_or_x_prefix():
    """法规文件名清理脚本应去掉开头数字、连接符或 X 标记。"""

    assert clean_legal_filename("01-中华人民共和国宪法.docx") == "中华人民共和国宪法.docx"
    assert clean_legal_filename("100中华人民共和国噪声污染防治法.docx") == "中华人民共和国噪声污染防治法.docx"
    assert clean_legal_filename("X中华人民共和国反不正当竞争法_20250627.docx") == "中华人民共和国反不正当竞争法_20250627.docx"
    assert clean_legal_filename("中华人民共和国公司法.docx") == "中华人民共和国公司法.docx"


def test_parse_legal_docx_falls_back_for_decision_documents(tmp_path):
    """没有条文编号的决定类文件应按段落兜底切分，避免入库时丢失。"""

    docx_path = tmp_path / "测试决定.docx"
    _write_minimal_docx(
        docx_path,
        [
            "全国人民代表大会常务委员会关于测试事项的决定",
            "为了测试没有条文编号的法规文件，作出如下决定。",
            "一、加强市场监管相关工作。",
            "二、依法处理投诉举报事项。",
        ],
    )

    document = parse_legal_docx(docx_path)

    assert len(document.chunks) >= 1
    assert document.chunks[0].article == "全文片段1"
    assert "投诉举报事项" in "\n".join(chunk.chunk_text for chunk in document.chunks)


def test_parse_legal_pdf_extracts_text(tmp_path):
    """文本型 PDF 应能提取正文并进入统一切分逻辑。"""

    pdf_path = tmp_path / "测试法规.pdf"
    _write_minimal_pdf(pdf_path, ["Test Law", "Article one text"])

    document = parse_legal_document(pdf_path)

    assert document.law_name == "Test Law"
    assert document.chunks[0].article == "全文片段1"
    assert "Article one text" in document.chunks[0].chunk_text


def test_rebuild_pdf_paragraphs_merges_split_legal_articles():
    """PDF 碎行重组应合并孤立标点、章节标题和第几条正文。"""

    paragraphs = _rebuild_pdf_paragraphs(
        [
            "中华人民共和国主席令",
            "《",
            "中华人民共和国黄河保护法",
            "》",
            "中华人民共和国黄河保护法",
            "（",
            "２０２２年１０月３０日通过",
            "）",
            "目",
            "录",
            "第一章",
            "总",
            "则",
            "第一章",
            "总",
            "则",
            "第一条",
            "为了加强黄河流域生态环境保护",
            "，",
            "保障黄河安澜",
            "—",
            "７１４",
            "—",
            "全国人民代表大会常务委员会公报",
            "２０２３",
            "·",
            "４",
            "，",
            "制定本法",
            "。",
            "第二条",
            "黄河流域相关活动",
            "，",
            "适用本法",
            "。",
        ]
    )

    assert paragraphs[0] == "中华人民共和国黄河保护法"
    assert paragraphs[1] == "（２０２２年１０月３０日通过）"
    assert "第一章　总则" in paragraphs
    assert "第一条　为了加强黄河流域生态环境保护，保障黄河安澜，制定本法。" in paragraphs
    assert not any("全国人民代表大会常务委员会公报" in paragraph for paragraph in paragraphs)
    assert not any("７１４" in paragraph for paragraph in paragraphs)
    assert "第二条　黄河流域相关活动，适用本法。" in paragraphs


def test_parse_legal_doc_uses_conversion_route(monkeypatch, tmp_path):
    """旧版 doc 文件应走转换读取路径，转换后的段落进入统一切分逻辑。"""

    doc_path = tmp_path / "测试法规.doc"
    doc_path.write_bytes(b"fake doc binary")
    monkeypatch.setattr(
        "app.legal_docx_parser._read_doc_paragraphs",
        lambda path: ["测试法规", "第一条　测试 doc 转换后的条文。"],
    )

    document = parse_legal_document(doc_path)

    assert document.law_name == "测试法规"
    assert document.chunks[0].article == "第一条"


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


def _write_minimal_docx(path, paragraphs):
    """写入测试用最小 docx 文件，只包含 document.xml 段落文本。"""

    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = "".join(
        f'<w:p><w:r><w:t>{text}</w:t></w:r></w:p>'
        for text in paragraphs
    )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{namespace}"><w:body>{body}</w:body></w:document>'
    )
    with ZipFile(path, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>",
        )
        archive.writestr("word/document.xml", document_xml)


def _write_minimal_pdf(path, lines):
    """写入测试用最小文本 PDF，供 pypdf 提取纯文本。"""

    commands = ["BT", "/F1 12 Tf", "72 720 Td"]
    for index, line in enumerate(lines):
        if index:
            commands.append("0 -18 Td")
        commands.append(f"({line}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("ascii")
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n",
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
        b"5 0 obj\n<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n"
        + stream + b"\nendstream\nendobj\n",
    ]
    content = b"%PDF-1.4\n"
    offsets = [0]
    for obj in objects:
        offsets.append(len(content))
        content += obj
    xref_position = len(content)
    content += f"xref\n0 {len(objects) + 1}\n".encode("ascii")
    content += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        content += f"{offset:010d} 00000 n \n".encode("ascii")
    content += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_position}\n%%EOF\n"
    ).encode("ascii")
    path.write_bytes(content)
