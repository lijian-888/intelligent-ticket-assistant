from __future__ import annotations

from app.actions import mock_transfer_action, mock_write_back_action
from app.graph import process_ticket
from app.llm_client import (
    AUTO_SUPPLEMENT_CONFIDENCE_THRESHOLD,
    AUTO_TRANSFER_CONFIDENCE_THRESHOLD,
)
from app.models import ProcessingResult, Ticket, TicketStatus
from app.supplement import build_supplement_task
from app.db import save_supplement_task


def smart_transfer_ticket(ticket: Ticket) -> ProcessingResult:
    """执行“智能流转”：高置信度自动执行，低置信度只给出推荐动作。"""

    result = process_ticket(ticket)
    confidence, threshold, reason = calculate_automation_confidence(result)
    result.automation_confidence = confidence

    if result.status == TicketStatus.RETURN_RECOMMENDED:
        result.automation_mode = "manual_review"
        result.automation_reason = f"退单必须由工作人员人工确认，系统仅给出建议：{reason}"
        _mark_manual_recommendation(result)
        return result

    if confidence < threshold:
        result.automation_mode = "manual_review"
        result.automation_reason = f"置信度 {confidence:.2f} 低于自动执行阈值 {threshold:.2f}，保留人工确认：{reason}"
        _mark_manual_recommendation(result)
        return result

    result.automation_mode = "auto_executed"
    result.automation_reason = f"置信度 {confidence:.2f} 达到自动执行阈值 {threshold:.2f}，已自动执行：{reason}"
    _execute_recommended_action(ticket, result)
    return result


def calculate_automation_confidence(result: ProcessingResult) -> tuple[float, float, str]:
    """根据 LLM 审计结果和流程明确性计算是否允许自动执行。"""

    confidence_scores: list[float] = []
    reasons: list[str] = []
    threshold = AUTO_TRANSFER_CONFIDENCE_THRESHOLD

    case_audit = result.structured.case_nature_llm_result.get("audit", {})
    case_output = result.structured.case_nature_llm_result.get("output") or {}
    if case_audit.get("accepted") and case_output.get("confidence") is not None:
        confidence_scores.append(float(case_output["confidence"]))
        reasons.append("投诉/举报分类已由 LLM 高置信度确认")
    else:
        return 0.0, threshold, "投诉/举报分类未达到自动执行要求"

    if result.status == TicketStatus.RETURN_RECOMMENDED:
        acceptance_audit = result.acceptance_precheck.get("audit", {})
        acceptance_output = result.acceptance_precheck.get("output") or {}
        if acceptance_audit.get("accepted") and acceptance_output.get("confidence") is not None:
            confidence_scores.append(float(acceptance_output["confidence"]))
            reasons.append("退单初筛已由 LLM 确认，但退单动作必须人工处理")
        else:
            return min(confidence_scores), threshold, "退单原因未达到人工确认要求"
    elif result.status == TicketStatus.NEED_SUPPLEMENT:
        threshold = AUTO_SUPPLEMENT_CONFIDENCE_THRESHOLD
        if not result.missing_fields:
            return 0.0, threshold, "未识别到可写入补充任务表的缺失字段"
        reasons.append("存在明确缺失核心字段")
    elif result.status == TicketStatus.READY_TO_TRANSFER:
        threshold = AUTO_TRANSFER_CONFIDENCE_THRESHOLD
        if not result.recommended_branch:
            return 0.0, threshold, "缺少明确建议承办单位"
        if result.jurisdiction != "市场监管职责范围":
            return 0.0, threshold, "职责范围不是明确的市场监管职责范围"
        reasons.append("职责范围和建议承办单位明确")

        review_audit = result.llm_review.get("audit", {})
        review_output = result.llm_review.get("output") or {}
        if review_audit.get("accepted") and review_output.get("confidence") is not None:
            confidence_scores.append(float(review_output["confidence"]))
            reasons.append("整体复核已由 LLM 高置信度确认")
        else:
            reasons.append("整体复核未启用或未通过，按分类置信度保守判断")
    else:
        return 0.0, threshold, "未知处理状态"

    return min(confidence_scores), threshold, "；".join(reasons)


def _mark_manual_recommendation(result: ProcessingResult) -> None:
    """低置信度时保持推荐动作，不做真实状态流转。"""

    for action in result.actions:
        action["executed"] = False
        action["note"] = f"置信度不足，建议人工确认后手动执行。{action.get('note', '')}"


def _execute_recommended_action(ticket: Ticket, result: ProcessingResult) -> None:
    """高置信度时模拟调用对应工单系统接口或写入补充任务表。"""

    if result.status == TicketStatus.RETURN_RECOMMENDED:
        return

    if result.status == TicketStatus.NEED_SUPPLEMENT:
        task = build_supplement_task(ticket, result)
        if task is not None:
            save_supplement_task(task)
        result.actions = [
            mock_write_back_action(
                ticket.ticket_no,
                "补充核心字段任务",
                result.missing_fields,
                executed=True,
            )
        ]
        result.actions[0]["note"] = "demo阶段已自动加入补充核心字段任务表。"
        return

    if result.status == TicketStatus.READY_TO_TRANSFER:
        result.actions = [
            mock_transfer_action(
                ticket.ticket_no,
                result.recommended_branch,
                result.transfer_reason,
                executed=True,
            )
        ]
