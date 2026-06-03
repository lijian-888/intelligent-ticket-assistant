from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional, TypedDict

from pydantic import BaseModel, Field


class CaseNature(str, Enum):
    """工单性质：明确标识每条工单最终按投诉、举报还是无法判断处理。"""

    COMPLAINT = "投诉"
    REPORT = "举报"
    UNKNOWN = "无法判断"


class TicketStatus(str, Enum):
    """当前 demo 的处理结论，用于决定后续是流转、补充信息还是建议退单。"""

    READY_TO_TRANSFER = "待流转"
    NEED_SUPPLEMENT = "待补充"
    RETURN_RECOMMENDED = "建议退单"


class Ticket(BaseModel):
    """原始工单数据模型，字段尽量贴近市监工单详情页展示内容。"""

    title: str
    content: str
    ticket_no: str
    status: str = ""
    ticket_type: str = ""
    channel: str = ""
    urgency: str = ""
    caller_phone: str = ""
    contact_phone: str = ""
    customer_name: str = ""
    customer_gender: str = ""
    business_type_l1: str = ""
    business_type_l2: str = ""
    business_type_l3: str = ""
    business_type_l4: str = ""
    age_range: str = ""
    source: str = ""
    created_at: str = ""
    due_at: str = ""
    appeal_at: str = ""
    region: str = ""
    domicile_address: str = ""
    longitude_latitude: str = ""
    appeal_emotion: str = ""
    appeal_count: Optional[int] = None
    appeal_purpose: str = ""
    id_type: str = ""
    id_no: str = ""
    public_customer_info: str = ""
    incident_at: str = ""
    incident_address: str = ""
    third_party_ticket_no: str = ""
    attachments: list[str] = Field(default_factory=list)


class StructuredTicket(BaseModel):
    """结构化后的核心工单信息，是后续校验、分派、预警的统一输入。"""

    ticket_no: str
    title: str
    raw_content: str
    case_nature: CaseNature
    case_nature_reason: str
    case_nature_source: str = "rule"
    case_nature_llm_result: dict[str, Any] = Field(default_factory=dict)
    complainant_name: str
    contact_phone: str
    incident_address: str
    region: str
    respondent: str
    appeal: str
    incident_at: str
    amount: Optional[float] = None
    keywords: list[str] = Field(default_factory=list)


class LegalReference(BaseModel):
    """知识库检索出的可能相关法律条款，供工作人员办理时参考。"""

    law_name: str
    article: str
    excerpt: str
    matched_keywords: list[str] = Field(default_factory=list)
    relevance_score: float = 0.0
    reason: str = ""


class ProcessingResult(BaseModel):
    """LangGraph 全流程处理后的结果，供接口返回或后续写回工单系统。"""

    ticket_no: str
    status: TicketStatus
    structured: StructuredTicket
    inferred_required_fields: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    recommended_supplement_fields: list[str] = Field(default_factory=list)
    supplement_call_script: str = ""
    jurisdiction: str = ""
    acceptance_precheck: dict[str, Any] = Field(default_factory=dict)
    recommended_branch: str = ""
    transfer_reason: str = ""
    emotion_level: Literal["低", "中", "高"]
    mediation_advice: str
    professional_claimant_risk: Literal["低", "中", "高"]
    professional_claimant_reasons: list[str] = Field(default_factory=list)
    legal_references: list[LegalReference] = Field(default_factory=list)
    return_reason: str = ""
    llm_review: dict[str, Any] = Field(default_factory=dict)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    automation_confidence: float = 0.0
    automation_mode: Literal["auto_executed", "manual_review"] = "manual_review"
    automation_reason: str = "未进入自动执行。"


class SupplementTask(BaseModel):
    """给工作人员使用的信息补充任务，用于电话核实缺失字段。"""

    ticket_no: str
    title: str
    complainant_name: str
    contact_phone: str
    missing_fields: list[str]
    recommended_supplement_fields: list[str] = Field(default_factory=list)
    call_script: str
    priority: Literal["普通", "优先"]
    reason: str
    source_status: TicketStatus


class TicketState(TypedDict, total=False):
    """LangGraph 节点之间传递的状态对象，每个节点只补充自己负责的字段。"""

    ticket: Ticket
    structured: StructuredTicket
    inferred_required_fields: dict[str, Any]
    missing_fields: list[str]
    recommended_supplement_fields: list[str]
    jurisdiction: str
    acceptance_precheck: dict[str, Any]
    recommended_branch: str
    transfer_reason: str
    emotion_level: Literal["低", "中", "高"]
    mediation_advice: str
    professional_claimant_risk: Literal["低", "中", "高"]
    professional_claimant_reasons: list[str]
    legal_references: list[LegalReference]
    return_reason: str
    llm_review: dict[str, Any]
    status: TicketStatus
    supplement_call_script: str
    actions: list[dict[str, Any]]
    result: ProcessingResult
