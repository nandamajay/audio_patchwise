"""
LangGraph graph with True A2A — backend as message bus.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

try:
    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.graph import END, StateGraph
except Exception:  # pragma: no cover
    SqliteSaver = None  # type: ignore
    StateGraph = None  # type: ignore
    END = "__END__"  # type: ignore

from agents.a2a_protocol import A2AMessage, SharedA2AContext
from agents.aryabhata_node import aryabhata_node
from agents.chanakya_a2a_node import chanakya_a2a_node


@dataclass
class PatchWiseState:
    session_id: str
    config: Any

    original_patch: str
    current_fixed_patch: Optional[str] = None

    current_round: int = 0
    max_rounds: int = 5

    shared_a2a_context: Optional[SharedA2AContext] = None

    current_review_report: Optional[Any] = None
    round_history: list[Any] = field(default_factory=list)

    version_intelligence: Optional[Any] = None

    a2a_messages: list[A2AMessage] = field(default_factory=list)
    llm_config: Optional[Any] = None


def initialize_session_node(state: PatchWiseState) -> PatchWiseState:
    if not state.shared_a2a_context:
        state.shared_a2a_context = SharedA2AContext(
            session_id=state.session_id,
            original_patch=state.original_patch,
            current_patch=state.current_fixed_patch or state.original_patch,
            round_number=state.current_round,
            challenge_timeout=getattr(state.config, "challenge_timeout", 60)
            if state.config
            else 60,
        )
    return state


def version_intelligence_node(state: PatchWiseState) -> PatchWiseState:
    return state


def increment_round_node(state: PatchWiseState) -> PatchWiseState:
    state.current_round += 1
    if state.shared_a2a_context:
        state.shared_a2a_context.round_number = state.current_round
        state.shared_a2a_context.current_patch = (
            state.current_fixed_patch or state.shared_a2a_context.current_patch
        )
    return state


def finalize_session_node(state: PatchWiseState) -> PatchWiseState:
    return state


def should_continue(state: PatchWiseState) -> str:
    if state.shared_a2a_context and state.shared_a2a_context.lgtm:
        return "end"
    if state.current_round >= state.max_rounds:
        return "end"
    if state.shared_a2a_context and state.shared_a2a_context.user_arbitration_pending:
        return "wait_for_user"
    return "continue"


def build_patchwise_graph():
    if StateGraph is None:  # pragma: no cover
        raise RuntimeError("langgraph is not available in this environment")

    checkpointer = None
    if SqliteSaver is not None:
        checkpointer = SqliteSaver.from_conn_string(
            "/workspace/data/db/patchwise_checkpoints.db"
        )

    graph = StateGraph(PatchWiseState)
    graph.add_node("initialize", initialize_session_node)
    graph.add_node("version_intelligence", version_intelligence_node)
    graph.add_node("chanakya_review", chanakya_a2a_node)
    graph.add_node("aryabhata_fix", aryabhata_node)
    graph.add_node("increment_round", increment_round_node)
    graph.add_node("finalize", finalize_session_node)

    graph.set_entry_point("initialize")
    graph.add_edge("initialize", "version_intelligence")
    graph.add_edge("version_intelligence", "chanakya_review")
    graph.add_edge("chanakya_review", "aryabhata_fix")
    graph.add_edge("aryabhata_fix", "increment_round")

    graph.add_conditional_edges(
        "increment_round",
        should_continue,
        {
            "continue": "chanakya_review",
            "end": "finalize",
            "wait_for_user": "finalize",
        },
    )
    graph.add_edge("finalize", END)

    if checkpointer is None:
        return graph.compile()
    return graph.compile(checkpointer=checkpointer)
