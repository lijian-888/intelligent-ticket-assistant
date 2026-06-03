from __future__ import annotations

from typing import Any

from fastapi.encoders import jsonable_encoder
from langgraph.graph import END, StateGraph

from app.models import ProcessingResult, Ticket, TicketState
from app.nodes import (
    analyze_emotion,
    assess_professional_claimant,
    build_result,
    decide_action,
    judge_jurisdiction,
    infer_missing_required_fields,
    precheck_acceptance,
    recommend_branch,
    retrieve_legal_references_node,
    review_with_llm,
    structure_ticket,
    validate_completeness,
)


def should_skip_completion(state: TicketState) -> str:
    """已有不予受理/退单原因时，跳过字段补全流程。"""

    return "skip_completion" if state.get("return_reason") else "need_completion"


def build_graph():
    """构建 LangGraph 工作流，定义每个处理节点及节点之间的执行顺序。"""

    graph = StateGraph(TicketState)
    graph.add_node("structure_ticket", structure_ticket)
    graph.add_node("retrieve_legal_references", retrieve_legal_references_node)
    graph.add_node("assess_professional_claimant", assess_professional_claimant)
    graph.add_node("precheck_acceptance", precheck_acceptance)
    graph.add_node("infer_missing_required_fields", infer_missing_required_fields)
    graph.add_node("validate_completeness", validate_completeness)
    graph.add_node("judge_jurisdiction", judge_jurisdiction)
    graph.add_node("recommend_branch", recommend_branch)
    graph.add_node("analyze_emotion", analyze_emotion)
    graph.add_node("review_with_llm", review_with_llm)
    graph.add_node("decide_action", decide_action)
    graph.add_node("build_result", build_result)

    graph.set_entry_point("structure_ticket")
    graph.add_edge("structure_ticket", "retrieve_legal_references")
    graph.add_edge("retrieve_legal_references", "assess_professional_claimant")
    graph.add_edge("assess_professional_claimant", "precheck_acceptance")
    graph.add_conditional_edges(
        "precheck_acceptance",
        should_skip_completion,
        {
            "skip_completion": "analyze_emotion",
            "need_completion": "infer_missing_required_fields",
        },
    )
    graph.add_edge("infer_missing_required_fields", "validate_completeness")
    graph.add_edge("validate_completeness", "judge_jurisdiction")
    graph.add_edge("judge_jurisdiction", "recommend_branch")
    graph.add_edge("recommend_branch", "analyze_emotion")
    graph.add_edge("analyze_emotion", "review_with_llm")
    graph.add_edge("review_with_llm", "decide_action")
    graph.add_edge("decide_action", "build_result")
    graph.add_edge("build_result", END)
    return graph.compile()


ticket_graph = build_graph()
"""编译后的 LangGraph 实例。接口处理工单时会复用这个对象。"""


def process_ticket(ticket: Ticket) -> ProcessingResult:
    """对单条工单执行完整 LangGraph 流程，并返回处理结果。"""

    final_state = ticket_graph.invoke({"ticket": ticket})
    return final_state["result"]


def process_ticket_steps(ticket: Ticket) -> list[dict[str, Any]]:
    """按 LangGraph 节点顺序返回单条工单的中间处理过程。"""

    steps: list[dict[str, Any]] = []
    for event in ticket_graph.stream({"ticket": ticket}, stream_mode="updates"):
        for node_name, output in event.items():
            steps.append(
                {


                    "node": node_name,
                    "output": jsonable_encoder(output),
                }
            )
    return steps
