from __future__ import annotations

from app.db import list_supplement_tasks_from_db, save_supplement_task
from app.graph import process_ticket
from app.models import ProcessingResult, SupplementTask, Ticket, TicketStatus


def build_supplement_task(ticket: Ticket, result: ProcessingResult | None = None) -> SupplementTask | None:
    """根据工单处理结果生成给工作人员的电话补充任务。"""

    result = result or process_ticket(ticket)
    if not result.missing_fields:
        return None

    priority = "优先" if result.emotion_level == "高" else "普通"
    contact_phone = result.structured.contact_phone or ticket.contact_phone or ticket.caller_phone
    call_script = result.supplement_call_script
    if not call_script:
        call_script = (
            f"请联系提交人核实并补充：{', '.join(result.missing_fields)}。"
            "通话时同步确认消费时间、商家准确名称和地址、具体诉求及是否有订单/票据/图片证据。"
        )
    if not contact_phone:
        call_script = (
            "当前工单缺少联系电话，请先通过原始渠道、来电记录或平台任务单回查联系方式。"
            f"{call_script}"
        )

    return SupplementTask(
        ticket_no=ticket.ticket_no,
        title=ticket.title,
        complainant_name=ticket.customer_name,
        contact_phone=contact_phone,
        missing_fields=result.missing_fields,
        recommended_supplement_fields=result.recommended_supplement_fields,
        call_script=call_script,
        priority=priority,
        reason="核心字段缺失，暂不满足流转条件，需要工作人员电话核实后补齐。",
        source_status=TicketStatus.NEED_SUPPLEMENT,
    )


def create_or_update_supplement_task(ticket: Ticket) -> SupplementTask | None:
    """生成补充任务并写入数据库，供任务列表接口查询。"""

    task = build_supplement_task(ticket)
    if task is None:
        return None
    return save_supplement_task(task)


def list_saved_supplement_tasks() -> list[SupplementTask]:
    """返回已经生成并保存的补充任务。"""

    return list_supplement_tasks_from_db()
