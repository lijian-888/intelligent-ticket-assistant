from __future__ import annotations

from typing import Any


def mock_transfer_action(ticket_no: str, branch: str, reason: str, executed: bool = False) -> dict[str, Any]:
    """模拟调用工单系统的流转接口；demo 阶段只生成动作，不真实执行。"""

    return {
        "tool": "transfer_ticket",
        "ticket_no": ticket_no,
        "target_branch": branch,
        "reason": reason,
        "executed": executed,
        "note": "demo阶段已模拟调用流转接口。" if executed else "demo阶段仅生成流转动作，不真实提交。",
    }


def mock_return_ticket_action(ticket_no: str, reason: str, executed: bool = False) -> dict[str, Any]:
    """模拟调用工单系统的退单接口；demo 阶段只生成动作，不真实执行。"""

    return {
        "tool": "return_ticket",
        "ticket_no": ticket_no,
        "reason": reason,
        "executed": executed,
        "note": "demo阶段已模拟调用退单接口。" if executed else "demo阶段仅生成退单动作，不真实提交。",
    }


def mock_write_back_action(ticket_no: str, field: str, value: Any, executed: bool = False) -> dict[str, Any]:
    """模拟调用工单系统的写回接口，用于记录缺失字段、预警或处理建议。"""

    return {
        "tool": "write_back_ticket",
        "ticket_no": ticket_no,
        "field": field,
        "value": value,
        "executed": executed,
        "note": "demo阶段已模拟调用写回接口。" if executed else "demo阶段仅生成写回动作，不真实提交。",
    }
