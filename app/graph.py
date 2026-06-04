from __future__ import annotations

from time import perf_counter
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


def timed_node(node_name: str, node_fn):
    """包装 LangGraph 节点，向控制台输出每个节点的耗时。"""

    def wrapped(state: TicketState) -> TicketState:
        ticket = state.get("ticket")
        ticket_no = ticket.ticket_no if ticket else "-"
        started = perf_counter()
        try:
            return node_fn(state)
        finally:
            duration_ms = round((perf_counter() - started) * 1000, 2)
            print(
                f"[graph node timing] ticket={ticket_no} node={node_name} duration_ms={duration_ms}",
                flush=True,
            )

    return wrapped


def parallel_join(state: TicketState) -> TicketState:
    """并行分支汇合节点，本身不修改状态。"""

    return {}


def should_skip_completion(state: TicketState) -> str:
    """已有不予受理/退单原因时，跳过字段补全流程。"""

    return "skip_completion" if state.get("return_reason") else "need_completion"


def build_graph():
    """构建 LangGraph 工作流，定义每个处理节点及节点之间的执行顺序。"""

    graph = StateGraph(TicketState)
    graph.add_node("structure_ticket", timed_node("structure_ticket", structure_ticket))
    graph.add_node("retrieve_legal_references", timed_node("retrieve_legal_references", retrieve_legal_references_node))
    graph.add_node("assess_professional_claimant", timed_node("assess_professional_claimant", assess_professional_claimant))
    graph.add_node("precheck_acceptance", timed_node("precheck_acceptance", precheck_acceptance))
    graph.add_node("parallel_join", timed_node("parallel_join", parallel_join))
    graph.add_node("infer_missing_required_fields", timed_node("infer_missing_required_fields", infer_missing_required_fields))
    graph.add_node("validate_completeness", timed_node("validate_completeness", validate_completeness))
    graph.add_node("judge_jurisdiction", timed_node("judge_jurisdiction", judge_jurisdiction))
    graph.add_node("recommend_branch", timed_node("recommend_branch", recommend_branch))
    graph.add_node("analyze_emotion", timed_node("analyze_emotion", analyze_emotion))
    graph.add_node("review_with_llm", timed_node("review_with_llm", review_with_llm))
    graph.add_node("decide_action", timed_node("decide_action", decide_action))
    graph.add_node("build_result", timed_node("build_result", build_result))

    graph.set_entry_point("structure_ticket")
    graph.add_edge("structure_ticket", "retrieve_legal_references")
    graph.add_edge("structure_ticket", "assess_professional_claimant")
    graph.add_edge("structure_ticket", "precheck_acceptance")
    graph.add_edge(["retrieve_legal_references", "assess_professional_claimant", "precheck_acceptance"], "parallel_join")
    graph.add_conditional_edges(
        "parallel_join",
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

    started = perf_counter()
    try:
        final_state = ticket_graph.invoke({"ticket": ticket})
        return final_state["result"]
    finally:
        duration_ms = round((perf_counter() - started) * 1000, 2)
        print(f"[graph total timing] ticket={ticket.ticket_no} duration_ms={duration_ms}", flush=True)


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
