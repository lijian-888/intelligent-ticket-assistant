from __future__ import annotations

import json
import re
from typing import Any, Literal, Optional

from pydantic import ValidationError

from app.actions import mock_return_ticket_action, mock_transfer_action, mock_write_back_action
from app.llm_client import (
    LLM_CLASSIFY_TIMEOUT_SECONDS,
    LLM_CONFIDENCE_THRESHOLD,
    LLM_ENABLE_REVIEW,
    LLM_FIELD_INFER_TIMEOUT_SECONDS,
    LLM_MODEL,
    LLM_REVIEW_TIMEOUT_SECONDS,
    call_llm_json,
    is_llm_configured,
)
from app.llm_schemas import (
    ACCEPTANCE_PRECHECK_PROMPT_VERSION,
    CLASSIFY_CASE_NATURE_PROMPT_VERSION,
    EMOTION_ANALYSIS_PROMPT_VERSION,
    MISSING_REQUIRED_FIELDS_PROMPT_VERSION,
    PROFESSIONAL_CLAIMANT_PROMPT_VERSION,
    REVIEW_PROMPT_VERSION,
    AcceptancePrecheckLlmOutput,
    AcceptancePrecheckLlmResult,
    CaseNatureLlmOutput,
    CaseNatureLlmResult,
    EmotionAnalysisLlmOutput,
    EmotionAnalysisLlmResult,
    MissingRequiredFieldsLlmOutput,
    MissingRequiredFieldsLlmResult,
    ProfessionalClaimantLlmOutput,
    ProfessionalClaimantLlmResult,
    LlmAudit,
    TicketReviewLlmOutput,
    TicketReviewLlmResult,
)
from app.legal_kb import retrieve_legal_references
from app.models import CaseNature, ProcessingResult, StructuredTicket, Ticket, TicketState, TicketStatus
from app.rules import (
    MARKET_REGULATION_KEYWORDS,
    NATIONAL_REGION_RULES,
    NON_MARKET_REGULATION_HINTS,
    RECOMMENDED_FIELDS,
    REQUIRED_FIELDS,
)


def classify_case_nature_by_rule(ticket: Ticket) -> tuple[CaseNature, str]:
    """规则兜底分类：在未配置 LLM 或 LLM 失败时识别投诉/举报。"""

    text = f"{ticket.title} {ticket.content} {ticket.appeal_purpose}"
    report_words = ["举报", "依法查处", "违法", "违规", "立案", "处罚", "无证", "过期食品"]
    complaint_words = ["投诉", "退款", "退货", "赔偿", "协调", "消费纠纷", "态度恶劣", "售后"]

    report_score = sum(1 for word in report_words if word in text)
    complaint_score = sum(1 for word in complaint_words if word in text)

    if report_score > complaint_score:
        return CaseNature.REPORT, "文本更强调违法违规线索、依法查处或行政处罚诉求。"
    if complaint_score > report_score:
        return CaseNature.COMPLAINT, "文本更强调自身消费权益受损、退款赔偿或协调处理诉求。"
    if report_score and complaint_score:
        return CaseNature.REPORT, "同时包含投诉和举报特征，按行政违法线索优先归为举报。"
    return CaseNature.UNKNOWN, "文本未提供足够线索区分投诉或举报。"


def classify_case_nature(ticket: Ticket) -> tuple[CaseNature, str]:
    """LLM 优先识别投诉/举报；没有配置或调用失败时自动回退到规则分类。"""

    detail = classify_case_nature_detail(ticket)
    return detail["case_nature"], detail["reason"]


def classify_case_nature_detail(ticket: Ticket) -> dict[str, Any]:
    """返回投诉/举报分类详情，包括是否使用 LLM、LLM 原始结果和兜底原因。"""

    audit = LlmAudit(
        prompt_version=CLASSIFY_CASE_NATURE_PROMPT_VERSION,
        model=LLM_MODEL,
        confidence_threshold=LLM_CONFIDENCE_THRESHOLD,
    )
    if not is_llm_configured():
        nature, reason = classify_case_nature_by_rule(ticket)
        audit.reject_reason = "未配置 LLM_BASE_URL 或 LLM_API_KEY"
        return {
            "case_nature": nature,
            "reason": reason,
            "source": "rule",
            "llm_result": CaseNatureLlmResult(enabled=False, audit=audit, error=audit.reject_reason).model_dump(mode="json"),
        }

    messages = [
        {
            "role": "system",
            "content": (
                "你是市场监督管理部门投诉举报工单分类助手。"
                "请判断工单性质，只能在“投诉”“举报”“无法判断”中选择一个。"
                "投诉通常强调消费者自身权益、退款、赔偿、调解；"
                "举报通常强调违法线索、查处、处罚、取缔。"
                "只输出 JSON，字段必须是：case_nature、confidence、reason。"
                "confidence 必须是 0 到 1 之间的小数。"
            ),
        },
        {
            "role": "user",
            "content": (
                "请按 schema 输出："
                '{"case_nature":"投诉|举报|无法判断","confidence":0.0,"reason":"判断依据"}'
                f"\n标题：{ticket.title}"
                f"\n内容：{ticket.content}"
                f"\n诉求：{ticket.appeal_purpose}"
                f"\n业务类型：{ticket.ticket_type}"
            ),
        },
    ]

    try:
        raw_result = call_llm_json(messages, timeout_seconds=LLM_CLASSIFY_TIMEOUT_SECONDS)
        output = CaseNatureLlmOutput.model_validate(raw_result)
        llm_result = CaseNatureLlmResult(output=output, raw=raw_result, audit=audit)
        if output.confidence < LLM_CONFIDENCE_THRESHOLD:
            llm_error = f"LLM 置信度 {output.confidence} 低于阈值 {LLM_CONFIDENCE_THRESHOLD}"
            llm_result.audit.reject_reason = llm_error
            llm_result.error = llm_error
        else:
            llm_result.audit.accepted = True
            print(
                f"[LLM case_nature] ticket={ticket.ticket_no} accepted={llm_result.model_dump_json()}",
                flush=True,
            )
            return {
                "case_nature": CaseNature(output.case_nature),
                "reason": f"LLM识别：{output.reason}",
                "source": "llm",
                "llm_result": llm_result.model_dump(mode="json"),
            }
    except ValidationError as exc:
        llm_error = f"LLM 输出 schema 校验失败：{exc.errors()}"
        audit.reject_reason = llm_error
        llm_result = CaseNatureLlmResult(raw=locals().get("raw_result", {}), audit=audit, error=llm_error)
    except Exception as exc:
        llm_error = f"{type(exc).__name__}: {exc}"
        audit.reject_reason = llm_error
        llm_result = CaseNatureLlmResult(raw=locals().get("raw_result", {}), audit=audit, error=llm_error)

    nature, reason = classify_case_nature_by_rule(ticket)
    fallback = {
        "case_nature": nature,
        "reason": f"{reason}（LLM分类失败，已回退规则：{llm_error}）",
        "source": "rule_fallback",
        "llm_result": llm_result.model_dump(mode="json"),
    }
    print(f"[LLM case_nature] ticket={ticket.ticket_no} fallback={json.dumps(fallback['llm_result'], ensure_ascii=False)}", flush=True)
    return fallback



def extract_respondent(ticket: Ticket) -> str:
    """从工单正文中粗略抽取被投诉/举报对象，后续可替换为 LLM 或 NER 抽取。"""

    text = ticket.content
    markers = ["在", "于"]
    for marker in markers:
        if marker in text and "购买" in text:
            start = text.find(marker) + len(marker)
            end = text.find("购买", start)
            candidate = text[start:end].strip(" ，,。")
            candidate = candidate.split("（", 1)[0].split("(", 1)[0].strip(" ，,。")
            if "消费" in candidate:
                candidate = candidate.split("消费", 1)[0].strip(" ，,。")
            if candidate in {"网上", "网络", "网购", "线上"}:
                continue
            if 2 <= len(candidate) <= 80:
                return candidate
    for suffix in ["店", "网店", "便利店", "餐饮店", "公司"]:
        index = text.find(suffix)
        if index > 0:
            start = max(0, index - 25)
            return text[start : index + len(suffix)].strip(" ，,。在于")
    return ""


def extract_amount(ticket: Ticket) -> Optional[float]:
    """从工单正文中抽取消费或充值金额；未识别到金额则返回 None。"""

    match = re.search(r"消费(\d+(?:\.\d+)?)元|充值.*?(\d+(?:\.\d+)?)元|购买.*?(\d+(?:\.\d+)?)元", ticket.content)
    if not match:
        return None
    for value in match.groups():
        if value:
            return float(value)
    return None


def extract_keywords(text: str) -> list[str]:
    """抽取和市场监管处理有关的关键词，用于结果摘要和后续风险解释。"""

    candidates = [
        "虚假宣传",
        "医疗功效",
        "过期食品",
        "退款",
        "赔偿",
        "十倍赔偿",
        "食品安全法",
        "标签",
        "无证",
        "价格",
        "发票",
        "质量",
    ]
    return [word for word in candidates if word in text]


def extract_product_or_service(ticket: Ticket) -> str:
    """从正文中粗略抽取商品或服务名称，抽不到时返回空字符串。"""

    text = ticket.content
    match = re.search(r"购买([^，。；\s]+)", text)
    if match:
        return match.group(1).strip(" ，。；")
    match = re.search(r"充值([^，。；\s]+)", text)
    if match:
        return match.group(1).strip(" ，。；")
    return ""


def get_required_field_values(ticket: Ticket, structured: StructuredTicket) -> dict[str, str]:
    """汇总阻断流转字段当前值，供缺失检查和 LLM 推断复用。"""

    return {
        "ticket_no": ticket.ticket_no,
        "title": ticket.title,
        "content": ticket.content,
        "contact_phone": structured.contact_phone,
        "incident_address": structured.incident_address,
        "region": structured.region,
        "appeal": structured.appeal,
    }


def infer_missing_required_fields(state: TicketState) -> TicketState:
    """LangGraph 节点：用 LLM 尝试推断缺失的阻断字段，低置信度不采纳。"""

    ticket = state["ticket"]
    structured = state["structured"]
    current_values = get_required_field_values(ticket, structured)
    missing_field_keys = [field for field in REQUIRED_FIELDS if not current_values.get(field)]
    audit = LlmAudit(
        prompt_version=MISSING_REQUIRED_FIELDS_PROMPT_VERSION,
        model=LLM_MODEL,
        confidence_threshold=LLM_CONFIDENCE_THRESHOLD,
    )

    if not missing_field_keys:
        audit.accepted = True
        return {
            "inferred_required_fields": MissingRequiredFieldsLlmResult(
                enabled=False,
                accepted_fields=[],
                audit=audit,
                error="没有缺失的阻断字段，无需调用 LLM 推断。",
            ).model_dump(mode="json")
        }

    if not is_llm_configured():
        audit.reject_reason = "未配置 LLM_BASE_URL 或 LLM_API_KEY"
        return {
            "inferred_required_fields": MissingRequiredFieldsLlmResult(
                enabled=False,
                audit=audit,
                error=audit.reject_reason,
            ).model_dump(mode="json")
        }

    allowed_fields = {field: REQUIRED_FIELDS[field] for field in missing_field_keys}
    messages = [
        {
            "role": "system",
            "content": (
                "你是市场监督管理部门工单字段补全助手。"
                "只能根据工单标题和工单内容推断缺失字段，不能编造。"
                "只能补全用户给出的 missing_fields 中的字段。"
                "每个字段必须给出 value、confidence、reason。"
                "confidence 必须是 0 到 1 的小数。只输出 JSON。"
            ),
        },
        {
            "role": "user",
            "content": (
                "请按 schema 输出："
                '{"inferred_fields":[{"field":"字段key","value":"推断值","confidence":0.0,"reason":"依据"}]}'
                f"\nmissing_fields：{json.dumps(allowed_fields, ensure_ascii=False)}"
                f"\n标题：{ticket.title}"
                f"\n工单内容：{ticket.content}"
                f"\n已有字段：{json.dumps(current_values, ensure_ascii=False)}"
            ),
        },
    ]

    try:
        raw_result = call_llm_json(messages, timeout_seconds=LLM_FIELD_INFER_TIMEOUT_SECONDS)
        output = MissingRequiredFieldsLlmOutput.model_validate(raw_result)
        accepted = []
        rejected = []
        for item in output.inferred_fields:
            if item.field not in allowed_fields:
                rejected.append(item)
                continue
            if not item.value.strip():
                rejected.append(item)
                continue
            if item.confidence < LLM_CONFIDENCE_THRESHOLD:
                rejected.append(item)
                continue
            accepted.append(item)
        audit.accepted = bool(accepted)
        if not accepted:
            audit.reject_reason = "LLM 未给出达到置信度阈值的可采纳字段。"
        result = MissingRequiredFieldsLlmResult(
            output=output,
            raw=raw_result,
            accepted_fields=accepted,
            rejected_fields=rejected,
            audit=audit,
        )
        return {"inferred_required_fields": result.model_dump(mode="json")}
    except ValidationError as exc:
        error = f"LLM 输出 schema 校验失败：{exc.errors()}"
    except Exception as exc:
        error = f"大模型字段推断失败：{type(exc).__name__}: {exc}"

    audit.reject_reason = error
    return {
        "inferred_required_fields": MissingRequiredFieldsLlmResult(
            raw=locals().get("raw_result", {}),
            audit=audit,
            error=error,
        ).model_dump(mode="json")
    }


def infer_appeal(ticket: Ticket) -> str:
    """当原始工单没有明确诉求字段时，从正文中推断诉求目的。"""

    text = ticket.content
    if "赔偿" in text:
        return "赔偿"
    if "退款" in text or "退还" in text:
        return "退款"
    if "依法查处" in text or "处理结果" in text:
        return "依法查处并反馈"
    if "要求处理" in text:
        return "要求处理"
    return ""


def structure_ticket(state: TicketState) -> TicketState:
    """LangGraph 节点：把原始工单整理成结构化字段。"""

    ticket = state["ticket"]
    classification = classify_case_nature_detail(ticket)
    text = f"{ticket.title} {ticket.content} {ticket.appeal_purpose}"
    structured = StructuredTicket(
        ticket_no=ticket.ticket_no,
        title=ticket.title,
        raw_content=ticket.content,
        case_nature=classification["case_nature"],
        case_nature_reason=classification["reason"],
        case_nature_source=classification["source"],
        case_nature_llm_result=classification["llm_result"],
        complainant_name=ticket.customer_name,
        contact_phone=ticket.contact_phone or ticket.caller_phone,
        incident_address=ticket.incident_address,
        region=ticket.region,
        respondent=extract_respondent(ticket),
        appeal=ticket.appeal_purpose or infer_appeal(ticket),
        incident_at=ticket.incident_at,
        amount=extract_amount(ticket),
        keywords=extract_keywords(text),
    )
    return {"structured": structured}


def validate_completeness(state: TicketState) -> TicketState:
    """LangGraph 节点：检查阻断字段和建议补充字段，并生成补充信息话术。"""

    ticket = state["ticket"]
    structured = state["structured"]
    values = get_required_field_values(ticket, structured)
    inferred = state.get("inferred_required_fields", {})
    for item in inferred.get("accepted_fields", []):
        field = item.get("field")
        value = item.get("value")
        if field in values and value and not values.get(field):
            values[field] = value

    recommended_values = {
        "customer_name": ticket.customer_name,
        "incident_at": structured.incident_at,
        "respondent": structured.respondent,
        "product_or_service": extract_product_or_service(ticket),
        "case_nature": structured.case_nature.value,
        "issue_type": ",".join(structured.keywords),
    }
    missing = [label for field, label in REQUIRED_FIELDS.items() if not values.get(field)]
    recommended_missing = [
        label for field, label in RECOMMENDED_FIELDS.items() if not recommended_values.get(field)
    ]
    script = ""
    if missing:
        script = (
            f"请联系提交人核实并补充：{', '.join(missing)}。"
            "通话时同步确认消费时间、商家准确名称和地址、具体诉求及是否有订单/票据/图片证据。"
        )
    elif inferred.get("accepted_fields"):
        inferred_labels = [
            REQUIRED_FIELDS[item["field"]]
            for item in inferred.get("accepted_fields", [])
            if item.get("field") in REQUIRED_FIELDS
        ]
        script = f"以下阻断字段由大模型推断补齐，流转前建议人工确认：{', '.join(inferred_labels)}。"
    return {
        "missing_fields": missing,
        "recommended_supplement_fields": recommended_missing,
        "supplement_call_script": script,
    }


def retrieve_legal_references_node(state: TicketState) -> TicketState:
    """LangGraph 节点：从 mock 法律知识库中检索工单可能涉及的法律条款。"""

    return {
        "legal_references": retrieve_legal_references(
            state["ticket"],
            state["structured"],
        )
    }


def judge_jurisdiction(state: TicketState) -> TicketState:
    """LangGraph 节点：判断是否属于市场监管职责范围，必要时给出退单原因。"""

    ticket = state["ticket"]
    structured = state["structured"]
    text = f"{ticket.title} {ticket.content} {ticket.ticket_type} {structured.incident_address} {structured.region}"

    for hint, reason in NON_MARKET_REGULATION_HINTS.items():
        if hint in text:
            return {"jurisdiction": "非市场监管职责", "return_reason": reason}

    if not any(keyword in text for keyword in MARKET_REGULATION_KEYWORDS):
        return {
            "jurisdiction": "需人工复核",
            "return_reason": "未识别到明确市场监管职责关键词，建议人工复核是否应退单或转办。",
        }

    return {"jurisdiction": "市场监管职责范围", "return_reason": ""}


def recommend_branch(state: TicketState) -> TicketState:
    """LangGraph 节点：根据全国通用区域规则推荐建议承办单位。"""

    ticket = state["ticket"]
    structured = state["structured"]
    text = f"{structured.incident_address} {structured.region} {ticket.content} {ticket.title}"
    branch = ""
    matched_keyword = ""
    for branch_name, keywords in NATIONAL_REGION_RULES:
        matched_keyword = next((keyword for keyword in keywords if keyword in text), "")
        if matched_keyword:
            branch = branch_name
            break
    reason = ""
    if branch:
        reason = f"根据事发地址或正文中的“{matched_keyword}”匹配建议承办单位。"
    elif structured.region:
        branch = f"{structured.region}市场监督管理部门"
        reason = "根据工单所属区域生成泛化承办单位建议，正式上线时应接入权威区划和网格路由服务。"
    return {"recommended_branch": branch, "transfer_reason": reason}


def analyze_emotion_by_rule(ticket: Ticket) -> tuple[Literal["低", "中", "高"], str]:
    """规则兜底：用关键词识别提交人情绪强度。"""

    text = f"{ticket.title} {ticket.content} {ticket.appeal_emotion}"
    high_words = ["非常生气", "愤怒", "投诉到底", "曝光", "媒体", "不处理", "继续投诉举报"]
    medium_words = ["多次沟通", "拖延", "要求尽快", "不满", "无果"]

    if any(word in text for word in high_words):
        level: Literal["低", "中", "高"] = "高"
        advice = "建议优先联系提交人，先安抚情绪并明确办理时限；同步加快核查商家主体和证据材料。"
    elif any(word in text for word in medium_words):
        level = "中"
        advice = "建议在常规时限内尽快回访，说明受理流程，围绕退款、赔偿或查处诉求组织调解。"
    else:
        level = "低"
        advice = "按常规流程处理，联系提交人确认关键事实后流转属地市场监管部门办理。"

    return level, advice


def analyze_emotion(state: TicketState) -> TicketState:
    """LangGraph 节点：LLM 优先识别提交人情绪强度，规则关键词兜底。"""

    ticket = state["ticket"]
    audit = LlmAudit(
        prompt_version=EMOTION_ANALYSIS_PROMPT_VERSION,
        model=LLM_MODEL,
        confidence_threshold=LLM_CONFIDENCE_THRESHOLD,
    )

    if is_llm_configured():
        messages = [
            {
                "role": "system",
                "content": (
                    "你是市场监管投诉举报工单情绪分析助手。"
                    "请根据提交人的标题、正文、诉求和已有情绪字段判断情绪等级，只能输出“低”“中”“高”。"
                    "低：表达平稳或只陈述事实；中：有不满、催办、多次沟通无果；"
                    "高：明显愤怒、强烈施压、威胁曝光/媒体/继续投诉举报或要求立即处理。"
                    "请给出适合工作人员使用的调解参考建议。只输出 JSON。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "请按 schema 输出："
                    '{"emotion_level":"低|中|高","confidence":0.0,"reason":"判断依据","mediation_advice":"调解建议"}'
                    f"\n标题：{ticket.title}"
                    f"\n工单内容：{ticket.content}"
                    f"\n诉求目的：{ticket.appeal_purpose}"
                    f"\n原始情绪字段：{ticket.appeal_emotion}"
                ),
            },
        ]
        try:
            raw_result = call_llm_json(messages, timeout_seconds=LLM_CLASSIFY_TIMEOUT_SECONDS)
            output = EmotionAnalysisLlmOutput.model_validate(raw_result)
            llm_result = EmotionAnalysisLlmResult(output=output, raw=raw_result, audit=audit)
            if output.confidence >= LLM_CONFIDENCE_THRESHOLD:
                llm_result.audit.accepted = True
                return {
                    "emotion_level": output.emotion_level,
                    "mediation_advice": output.mediation_advice,
                    "emotion_analysis": llm_result.model_dump(mode="json"),
                }
            llm_result.error = f"LLM 置信度 {output.confidence} 低于阈值 {LLM_CONFIDENCE_THRESHOLD}"
            llm_result.audit.reject_reason = llm_result.error
        except ValidationError as exc:
            error = f"LLM 输出 schema 校验失败：{exc.errors()}"
            audit.reject_reason = error
            llm_result = EmotionAnalysisLlmResult(raw=locals().get("raw_result", {}), audit=audit, error=error)
        except Exception as exc:
            error = f"大模型情绪分析失败：{type(exc).__name__}: {exc}"
            audit.reject_reason = error
            llm_result = EmotionAnalysisLlmResult(raw=locals().get("raw_result", {}), audit=audit, error=error)
    else:
        audit.reject_reason = "未配置 LLM_BASE_URL 或 LLM_API_KEY"
        llm_result = EmotionAnalysisLlmResult(enabled=False, audit=audit, error=audit.reject_reason)

    level, advice = analyze_emotion_by_rule(ticket)
    return {
        "emotion_level": level,
        "mediation_advice": f"{advice}（LLM情绪分析未采纳，已使用规则兜底）",
        "emotion_analysis": llm_result.model_dump(mode="json"),
    }


def assess_professional_claimant_by_rule(ticket: Ticket, structured: StructuredTicket) -> tuple[Literal["低", "中", "高"], list[str]]:
    """规则兜底：用可解释评分识别疑似职业打假/职业索赔风险。"""

    text = f"{ticket.title} {ticket.content} {ticket.appeal_purpose}"
    reasons: list[str] = []
    score = 0

    if ticket.appeal_count is None:
        reasons.append("未提供历史投诉数据，本次仅基于单条工单文本信号进行风险提示。")
    elif ticket.appeal_count >= 10:
        score += 30
        reasons.append(f"历史/本渠道诉求次数较高：{ticket.appeal_count}次。")
    elif ticket.appeal_count >= 5:
        score += 15
        reasons.append(f"历史/本渠道诉求次数偏高：{ticket.appeal_count}次。")
    elif ticket.appeal_count >= 3:
        score += 8
        reasons.append(f"历史/本渠道存在多次诉求：{ticket.appeal_count}次。")

    weighted_phrases = {
        "十倍赔偿": 18,
        "退一赔三": 15,
        "食品安全法第一百四十八条": 12,
        "食品安全法148条": 12,
        "消费者权益保护法第五十五条": 10,
        "消法55条": 10,
        "惩罚性赔偿": 10,
        "索赔": 8,
    }
    for phrase, weight in weighted_phrases.items():
        if phrase in text:
            score += weight
            reasons.append(f"文本出现职业索赔高频表述：{phrase}。")

    pattern_phrases = {
        "多次购买不同店铺": 20,
        "继续投诉举报": 8,
        "批量": 10,
        "同款商品": 8,
        "同类商品": 8,
        "明知": 8,
        "知假买假": 15,
    }
    for phrase, weight in pattern_phrases.items():
        if phrase in text:
            score += weight
            reasons.append(f"文本呈现模式化或重复维权特征：{phrase}。")

    professional_terms = ["行政复议", "行政诉讼", "信息公开", "立案查处", "举报奖励", "法律依据"]
    matched_professional_terms = [phrase for phrase in professional_terms if phrase in text]
    if matched_professional_terms:
        score += min(len(matched_professional_terms) * 5, 15)
        reasons.append(f"文本出现较专业的程序性表述：{', '.join(matched_professional_terms)}。")

    defect_terms = ["标签", "配料表", "执行标准", "生产日期", "净含量", "广告法", "虚假宣传", "医疗功效"]
    matched_defect_terms = [phrase for phrase in defect_terms if phrase in text]
    if matched_defect_terms:
        score += min(len(matched_defect_terms) * 6, 18)
        reasons.append(f"问题集中在职业索赔常见关注点：{', '.join(matched_defect_terms)}。")

    pressure_terms = ["曝光", "媒体", "不处理", "投诉到底", "起诉", "复议"]
    matched_pressure_terms = [phrase for phrase in pressure_terms if phrase in text]
    if matched_pressure_terms:
        score += min(len(matched_pressure_terms) * 5, 15)
        reasons.append(f"文本包含施压式维权表述：{', '.join(matched_pressure_terms)}。")

    if structured.amount is not None and structured.amount <= 50 and any(phrase in text for phrase in ["十倍赔偿", "退一赔三", "惩罚性赔偿"]):
        score += 10
        reasons.append(f"消费金额较低（{structured.amount}元）但诉求指向惩罚性赔偿。")

    reasons.append(f"疑似职业索赔风险评分：{score}。")

    if score >= 55:
        risk: Literal["低", "中", "高"] = "高"
    elif score >= 30:
        risk = "中"
    else:
        risk = "低"

    return risk, reasons


def assess_professional_claimant(state: TicketState) -> TicketState:
    """LangGraph 节点：LLM 优先识别疑似职业打假/职业索赔风险，规则评分兜底。"""

    ticket = state["ticket"]
    structured = state["structured"]
    audit = LlmAudit(
        prompt_version=PROFESSIONAL_CLAIMANT_PROMPT_VERSION,
        model=LLM_MODEL,
        confidence_threshold=LLM_CONFIDENCE_THRESHOLD,
    )

    if is_llm_configured():
        messages = [
            {
                "role": "system",
                "content": (
                    "你是市场监管投诉举报工单职业打假/职业索赔风险识别助手。"
                    "你的结论只用于提醒工作人员关注沟通方式和证据核验，不能作为退单、不受理或降低处理优先级依据。"
                    "请基于单条工单文本、消费金额、诉求次数、法律术语、批量维权特征、惩罚性赔偿话术等判断风险等级。"
                    "如果没有历史投诉数据，不能仅凭普通投诉直接判高风险；"
                    "但文本出现多次购买、知假买假、十倍赔偿、专业法条、批量维权等强信号时，可以提高风险等级。"
                    "只输出 JSON。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "请按 schema 输出："
                    '{"professional_claimant_risk":"低|中|高","confidence":0.0,"reasons":["判断依据"]}'
                    f"\n标题：{ticket.title}"
                    f"\n工单内容：{ticket.content}"
                    f"\n诉求目的：{ticket.appeal_purpose}"
                    f"\n诉求次数：{ticket.appeal_count}"
                    f"\n消费金额：{structured.amount}"
                    f"\n关键词：{json.dumps(structured.keywords, ensure_ascii=False)}"
                    f"\n工单性质：{structured.case_nature.value}"
                ),
            },
        ]
        try:
            raw_result = call_llm_json(messages, timeout_seconds=LLM_CLASSIFY_TIMEOUT_SECONDS)
            output = ProfessionalClaimantLlmOutput.model_validate(raw_result)
            llm_result = ProfessionalClaimantLlmResult(output=output, raw=raw_result, audit=audit)
            if output.confidence >= LLM_CONFIDENCE_THRESHOLD:
                llm_result.audit.accepted = True
                return {
                    "professional_claimant_risk": output.professional_claimant_risk,
                    "professional_claimant_reasons": output.reasons,
                    "professional_claimant_llm_result": llm_result.model_dump(mode="json"),
                }
            llm_result.error = f"LLM 置信度 {output.confidence} 低于阈值 {LLM_CONFIDENCE_THRESHOLD}"
            llm_result.audit.reject_reason = llm_result.error
        except ValidationError as exc:
            error = f"LLM 输出 schema 校验失败：{exc.errors()}"
            audit.reject_reason = error
            llm_result = ProfessionalClaimantLlmResult(raw=locals().get("raw_result", {}), audit=audit, error=error)
        except Exception as exc:
            error = f"大模型职业索赔风险识别失败：{type(exc).__name__}: {exc}"
            audit.reject_reason = error
            llm_result = ProfessionalClaimantLlmResult(raw=locals().get("raw_result", {}), audit=audit, error=error)
    else:
        audit.reject_reason = "未配置 LLM_BASE_URL 或 LLM_API_KEY"
        llm_result = ProfessionalClaimantLlmResult(enabled=False, audit=audit, error=audit.reject_reason)

    risk, reasons = assess_professional_claimant_by_rule(ticket, structured)
    return {
        "professional_claimant_risk": risk,
        "professional_claimant_reasons": [*reasons, "LLM职业索赔风险识别未采纳，已使用规则评分兜底。"],
        "professional_claimant_llm_result": llm_result.model_dump(mode="json"),
    }


def precheck_acceptance_by_rule(state: TicketState) -> tuple[bool, str]:
    """规则兜底：按投诉/举报类型判断是否存在明显不予受理情形。"""

    ticket = state["ticket"]
    structured = state["structured"]
    text = f"{ticket.title} {ticket.content} {ticket.ticket_type} {ticket.appeal_purpose}"
    reasons: list[str] = []

    for hint, reason in NON_MARKET_REGULATION_HINTS.items():
        if hint in text:
            reasons.append(f"不属于市场监管职责：{reason}")

    duplicate_hints = ["已受理", "已经受理", "已处理", "已经处理", "法院已受理", "仲裁已受理", "消协已受理"]
    if any(hint in text for hint in duplicate_hints):
        reasons.append("同一事项疑似已由法院、仲裁机构、市场监管部门、其他行政机关或消协受理/处理。")

    if any(hint in text for hint in ["超过三年", "三年前", "超过2年", "超过两年"]):
        reasons.append("事项可能超过投诉/举报受理或行政处罚时效，需要人工核实。")

    if any(hint in text for hint in ["虚假材料", "冒用他人", "拒不配合核验", "身份无法核验"]):
        reasons.append("存在虚假材料、冒名或拒不配合身份核验风险。")

    case_nature = structured.case_nature
    if case_nature == CaseNature.COMPLAINT:
        if any(hint in text for hint in ["不能证明", "无消费凭证", "无法证明交易", "不存在消费关系"]):
            reasons.append("不能证明与被投诉人之间存在消费者权益争议。")

    elif case_nature == CaseNature.REPORT:
        report_unaccepted_rules = {
            "不属于市场监管职责": ["卫健", "药品门管", "药品部监管", "公安", "税务", "信访", "物业", "工资"],
            "重复举报": ["重复举报", "已举报", "已经举报"],
            "已由其他机关处理": ["纪检监察已处理", "公安已处理", "税务已处理", "其他机关已处理"],
            "已进入司法/复议程序": ["法院已受理", "行政复议已受理", "司法程序"],
            "纯民事纠纷": ["合同履行纠纷", "债务纠纷", "邻里纠纷", "私人纠纷"],
            "信访事项": ["信访事项", "信访渠道"],
        }
        for rule, hints in report_unaccepted_rules.items():
            if any(hint in text for hint in hints):
                reasons.append(f"举报不予受理情形：{rule}。")

    if reasons:
        return True, "；".join(reasons)

    return False, ""


def precheck_acceptance(state: TicketState) -> TicketState:
    """LangGraph 节点：LLM 优先判断不予受理/建议退单，规则仅作为兜底。"""

    ticket = state["ticket"]
    structured = state["structured"]
    audit = LlmAudit(
        prompt_version=ACCEPTANCE_PRECHECK_PROMPT_VERSION,
        model=LLM_MODEL,
        confidence_threshold=LLM_CONFIDENCE_THRESHOLD,
    )

    if is_llm_configured():
        messages = [
            {
                "role": "system",
                "content": (
                    "你是市场监管投诉举报受理初筛助手。"
                    "请根据工单性质分别判断是否存在不予受理/建议退单情形。"
                    "投诉重点判断：是否不属市场监管职责、是否无处理权限、是否已被其他机关/消协/法院/仲裁处理、"
                    "是否超过三年、是否材料虚假或冒名、是否不能证明与被投诉人之间存在消费者权益争议。"
                    "举报重点判断：是否不属市场监管职责、重复举报、已由其他机关处理、超过行政处罚时效、"
                    "已进入司法/复议程序、纯民事纠纷、信访事项。"
                    "举报缺少被举报对象、商家名称、链接、地址、交易记录或证据时，不要判定退单，应交由后续核心字段补充流程处理。"
                    "注意：疑似职业打假人或职业索赔人只能作为工作人员关注提醒，不能作为退单或不予受理依据。"
                    "只输出 JSON。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "请按 schema 输出："
                    '{"should_return":false,"confidence":0.0,"reason":"判断依据",'
                    '"rule_category":"适用的不予受理类别或无",'
                    '"handling_suggestion":"后续处理建议"}'
                    f"\n工单性质：{structured.case_nature.value}"
                    f"\n标题：{ticket.title}"
                    f"\n工单内容：{ticket.content}"
                    f"\n工单类型：{ticket.ticket_type}"
                    f"\n诉求目的：{ticket.appeal_purpose}"
                ),
            },
        ]
        try:
            raw_result = call_llm_json(messages, timeout_seconds=LLM_CLASSIFY_TIMEOUT_SECONDS)
            output = AcceptancePrecheckLlmOutput.model_validate(raw_result)
            llm_result = AcceptancePrecheckLlmResult(output=output, raw=raw_result, audit=audit)
            if output.confidence >= LLM_CONFIDENCE_THRESHOLD:
                llm_result.audit.accepted = True
                if output.should_return and _is_report_missing_information_reason(structured.case_nature, output.reason, output.rule_category):
                    llm_result.audit.accepted = False
                    llm_result.audit.reject_reason = "举报缺少对象、链接、证据等信息时应进入补充流程，不直接退单。"
                    llm_result.error = llm_result.audit.reject_reason
                    return {
                        "return_reason": "",
                        "acceptance_precheck": llm_result.model_dump(mode="json"),
                    }
                if output.should_return:
                    return {
                        "jurisdiction": "不予受理/建议退单",
                        "return_reason": output.reason,
                        "acceptance_precheck": llm_result.model_dump(mode="json"),
                    }
                return {
                    "return_reason": "",
                    "acceptance_precheck": llm_result.model_dump(mode="json"),
                }
            llm_result.error = f"LLM 置信度 {output.confidence} 低于阈值 {LLM_CONFIDENCE_THRESHOLD}"
            llm_result.audit.reject_reason = llm_result.error
        except ValidationError as exc:
            error = f"LLM 输出 schema 校验失败：{exc.errors()}"
            audit.reject_reason = error
            llm_result = AcceptancePrecheckLlmResult(raw=locals().get("raw_result", {}), audit=audit, error=error)
        except Exception as exc:
            error = f"大模型受理初筛失败：{type(exc).__name__}: {exc}"
            audit.reject_reason = error
            llm_result = AcceptancePrecheckLlmResult(raw=locals().get("raw_result", {}), audit=audit, error=error)
    else:
        audit.reject_reason = "未配置 LLM_BASE_URL 或 LLM_API_KEY"
        llm_result = AcceptancePrecheckLlmResult(enabled=False, audit=audit, error=audit.reject_reason)

    should_return, reason = precheck_acceptance_by_rule(state)
    result = {
        "acceptance_precheck": llm_result.model_dump(mode="json"),
        "return_reason": reason if should_return else "",
    }
    if should_return:
        result["jurisdiction"] = "不予受理/建议退单"
    return result


def _is_report_missing_information_reason(case_nature: CaseNature, reason: str, rule_category: str) -> bool:
    """举报缺少对象、链接或证据时应补充信息，不作为退单依据。"""

    if case_nature != CaseNature.REPORT:
        return False
    text = f"{reason} {rule_category}"
    missing_hints = [
        "无明确被举报对象",
        "被举报对象",
        "商家名称",
        "经营者名称",
        "链接",
        "地址",
        "交易记录",
        "证据",
        "具体商品",
        "具体线索",
        "未提供",
        "缺少",
    ]
    hard_return_hints = ["不属于市场监管", "重复举报", "已由其他机关", "行政处罚时效", "司法", "复议", "信访", "纯民事"]
    return any(hint in text for hint in missing_hints) and not any(hint in text for hint in hard_return_hints)


def review_with_llm(state: TicketState) -> TicketState:
    """LangGraph 节点：让大模型复核规则结果，并补充更自然的办理建议。"""

    audit = LlmAudit(
        prompt_version=REVIEW_PROMPT_VERSION,
        model=LLM_MODEL,
        confidence_threshold=LLM_CONFIDENCE_THRESHOLD,
    )
    if not LLM_ENABLE_REVIEW:
        audit.reject_reason = "LLM_ENABLE_REVIEW=false，已跳过整体复核。"
        return {
            "llm_review": TicketReviewLlmResult(
                enabled=False,
                audit=audit,
                error=audit.reject_reason,
            ).model_dump(mode="json")
        }
    if not is_llm_configured():
        audit.reject_reason = "未配置 LLM_BASE_URL 或 LLM_API_KEY"
        return {
            "llm_review": TicketReviewLlmResult(
                enabled=False,
                audit=audit,
                error=audit.reject_reason,
            ).model_dump(mode="json")
        }

    ticket = state["ticket"]
    structured = state["structured"]
    rule_snapshot = {
        "case_nature": structured.case_nature.value,
        "case_nature_reason": structured.case_nature_reason,
        "missing_fields": state.get("missing_fields", []),
        "jurisdiction": state.get("jurisdiction", ""),
        "recommended_branch": state.get("recommended_branch", ""),
        "emotion_level": state.get("emotion_level", ""),
        "professional_claimant_risk": state.get("professional_claimant_risk", ""),
        "return_reason": state.get("return_reason", ""),
    }
    prompt_payload = {
        "ticket": ticket.model_dump(),
        "structured": structured.model_dump(mode="json"),
        "rule_snapshot": rule_snapshot,
    }
    messages = [
        {
            "role": "system",
            "content": (
                "你是市场监督管理部门投诉举报工单辅助办理助手。"
                "请基于工单内容复核规则判断，只输出 JSON，不要输出 Markdown。"
                "必须输出字段：case_nature_review、confidence、case_nature_reason_review、"
                "handling_summary、mediation_advice_review、risk_notes、return_reason_review。"
                "confidence 必须是 0 到 1 之间的小数。"
            ),
        },
        {
            "role": "user",
            "content": (
                "请按 schema 输出："
                '{"case_nature_review":"投诉|举报|无法判断","confidence":0.0,'
                '"case_nature_reason_review":"...",'
                '"handling_summary":"...",'
                '"mediation_advice_review":"...",'
                '"risk_notes":["..."],'
                '"return_reason_review":"..."}'
                f"\n输入数据：{json.dumps(prompt_payload, ensure_ascii=False)}"
            ),
        },
    ]

    try:
        raw_review = call_llm_json(messages, timeout_seconds=LLM_REVIEW_TIMEOUT_SECONDS)
        output = TicketReviewLlmOutput.model_validate(raw_review)
        review = TicketReviewLlmResult(output=output, raw=raw_review, audit=audit)
        if output.confidence < LLM_CONFIDENCE_THRESHOLD:
            review.error = f"LLM 置信度 {output.confidence} 低于阈值 {LLM_CONFIDENCE_THRESHOLD}"
            review.audit.reject_reason = review.error
        else:
            review.audit.accepted = True
        return {"llm_review": review.model_dump(mode="json")}
    except ValidationError as exc:
        error = f"LLM 输出 schema 校验失败：{exc.errors()}"
        audit.reject_reason = error
        return {
            "llm_review": TicketReviewLlmResult(
                raw=locals().get("raw_review", {}),
                audit=audit,
                error=error,
            ).model_dump(mode="json")
        }
    except Exception as exc:
        error = f"大模型调用失败，已使用规则结果：{type(exc).__name__}: {exc}"
        audit.reject_reason = error
        return {
            "llm_review": TicketReviewLlmResult(
                raw=locals().get("raw_review", {}),
                audit=audit,
                error=error,
            ).model_dump(mode="json")
        }


def decide_action(state: TicketState) -> TicketState:
    """LangGraph 节点：综合前面判断，决定生成流转、补充信息或退单动作。"""

    missing = state.get("missing_fields", [])
    return_reason = state.get("return_reason", "")
    actions: list[dict[str, Any]] = []

    if return_reason and state.get("jurisdiction") != "市场监管职责范围":
        status = TicketStatus.RETURN_RECOMMENDED
        actions.append(mock_return_ticket_action(state["ticket"].ticket_no, return_reason))
    elif missing:
        status = TicketStatus.NEED_SUPPLEMENT
        actions.append(mock_write_back_action(state["ticket"].ticket_no, "缺失信息", missing))
    else:
        status = TicketStatus.READY_TO_TRANSFER
        actions.append(
            mock_transfer_action(
                state["ticket"].ticket_no,
                state.get("recommended_branch", ""),
                state.get("transfer_reason", ""),
            )
        )

    return {"status": status, "actions": actions}


def build_result(state: TicketState) -> TicketState:
    """LangGraph 节点：把分散在 state 中的节点输出组装成统一返回结果。"""

    result = ProcessingResult(
        ticket_no=state["ticket"].ticket_no,
        status=state["status"],
        structured=state["structured"],
        inferred_required_fields=state.get("inferred_required_fields", {}),
        missing_fields=state.get("missing_fields", []),
        recommended_supplement_fields=state.get("recommended_supplement_fields", []),
        supplement_call_script=state.get("supplement_call_script", ""),
        jurisdiction=state.get("jurisdiction", ""),
        acceptance_precheck=state.get("acceptance_precheck", {}),
        recommended_branch=state.get("recommended_branch", ""),
        transfer_reason=state.get("transfer_reason", ""),
        emotion_level=state["emotion_level"],
        emotion_analysis=state.get("emotion_analysis", {}),
        mediation_advice=state["mediation_advice"],
        professional_claimant_risk=state["professional_claimant_risk"],
        professional_claimant_llm_result=state.get("professional_claimant_llm_result", {}),
        professional_claimant_reasons=state.get("professional_claimant_reasons", []),
        legal_references=state.get("legal_references", []),
        return_reason=state.get("return_reason", ""),
        llm_review=state.get("llm_review", {}),
        actions=state.get("actions", []),
    )
    return {"result": result}
