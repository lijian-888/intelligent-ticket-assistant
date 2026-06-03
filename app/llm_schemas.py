from __future__ import annotations

from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


CLASSIFY_CASE_NATURE_PROMPT_VERSION = "case_nature_classifier_v1"
REVIEW_PROMPT_VERSION = "ticket_review_v1"
MISSING_REQUIRED_FIELDS_PROMPT_VERSION = "missing_required_fields_infer_v1"
ACCEPTANCE_PRECHECK_PROMPT_VERSION = "acceptance_precheck_v1"
DEFAULT_LLM_CONFIDENCE_THRESHOLD = 0.75


class LlmAudit(BaseModel):
    """大模型调用审计信息，用于记录是否采纳、prompt 版本和失败原因。"""

    audit_id: str = Field(default_factory=lambda: uuid4().hex)
    prompt_version: str
    model: str = ""
    confidence_threshold: float = DEFAULT_LLM_CONFIDENCE_THRESHOLD
    accepted: bool = False
    reject_reason: str = ""


class CaseNatureLlmOutput(BaseModel):
    """投诉/举报分类的大模型输出 schema。"""

    case_nature: Literal["投诉", "举报", "无法判断"]
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1)


class CaseNatureLlmResult(BaseModel):
    """投诉/举报分类的完整模型结果，包含原始输出和审计状态。"""

    enabled: bool = True
    output: CaseNatureLlmOutput | None = None
    raw: dict = Field(default_factory=dict)
    audit: LlmAudit
    error: str = ""


class TicketReviewLlmOutput(BaseModel):
    """整体工单复核的大模型输出 schema。"""

    case_nature_review: Literal["投诉", "举报", "无法判断"]
    confidence: float = Field(ge=0, le=1)
    case_nature_reason_review: str = Field(min_length=1)
    handling_summary: str = Field(min_length=1)
    mediation_advice_review: str = Field(min_length=1)
    risk_notes: list[str] = Field(default_factory=list)
    return_reason_review: str = ""


class TicketReviewLlmResult(BaseModel):
    """整体工单复核的完整模型结果，包含原始输出和审计状态。"""

    enabled: bool = True
    output: TicketReviewLlmOutput | None = None
    raw: dict = Field(default_factory=dict)
    audit: LlmAudit
    error: str = ""


class InferredRequiredField(BaseModel):
    """单个缺失阻断字段的大模型推断结果。"""

    field: str
    value: str
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1)


class MissingRequiredFieldsLlmOutput(BaseModel):
    """缺失阻断字段的大模型推断输出 schema。"""

    inferred_fields: list[InferredRequiredField] = Field(default_factory=list)


class MissingRequiredFieldsLlmResult(BaseModel):
    """缺失阻断字段推断的完整模型结果，包含原始输出和审计状态。"""

    enabled: bool = True
    output: MissingRequiredFieldsLlmOutput | None = None
    raw: dict = Field(default_factory=dict)
    accepted_fields: list[InferredRequiredField] = Field(default_factory=list)
    rejected_fields: list[InferredRequiredField] = Field(default_factory=list)
    audit: LlmAudit
    error: str = ""


class AcceptancePrecheckLlmOutput(BaseModel):
    """投诉/举报不予受理初筛的大模型输出 schema。"""

    should_return: bool
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1)
    rule_category: str = Field(min_length=1)
    handling_suggestion: str = Field(min_length=1)


class AcceptancePrecheckLlmResult(BaseModel):
    """投诉/举报不予受理初筛的完整模型结果。"""

    enabled: bool = True
    output: AcceptancePrecheckLlmOutput | None = None
    raw: dict = Field(default_factory=dict)
    audit: LlmAudit
    error: str = ""
