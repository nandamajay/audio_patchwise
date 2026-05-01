import asyncio

from langgraph.graph import END, StateGraph

from .aryabhata import aryabhata_fix_node
from .chanakya import chanakya_review_node
from .state import PatchWiseState


def _chanakya_review_sync(state: PatchWiseState) -> PatchWiseState:
    """
    LangGraph sync invoke path expects synchronous node handlers.
    Wrap async CHANAKYA node for compatibility with invoke().
    """
    return asyncio.run(chanakya_review_node(state))

def should_continue(state: PatchWiseState) -> str:
    """
    LangGraph conditional edge - decides next node.
    HARD CAP: never exceed max_rounds.
    """
    current_round = state.get("current_round", 0)
    max_rounds = state.get("max_rounds", 5)
    last_review = state.get("latest_review", {})

    if current_round >= max_rounds:
        state["current_round"] = max_rounds
        state["session_status"] = "MAX_ROUNDS_REACHED"
        return "end"

    if state.get("verdict") == "LGTM" or last_review.get("verdict") == "LGTM":
        state["session_status"] = "LGTM"
        return "end"

    if not last_review.get("issues") and not last_review.get("findings") and state.get("verdict") == "LGTM":
        state["session_status"] = "LGTM"
        return "end"

    return "aryabhata_fix"


def increment_round_safely(state: PatchWiseState) -> PatchWiseState:
    """Increment round with hard cap enforcement."""
    max_rounds = state.get("max_rounds", 5)
    current = state.get("current_round", 0)
    state["current_round"] = min(current + 1, max_rounds)
    return state

def build_patchwise_graph():
    graph = StateGraph(PatchWiseState)
    graph.add_node("chanakya_review", _chanakya_review_sync)
    graph.add_node("aryabhata_fix", aryabhata_fix_node)
    graph.set_entry_point("chanakya_review")
    graph.add_conditional_edges(
        "chanakya_review",
        should_continue,
        {"aryabhata_fix": "aryabhata_fix", "end": END}
    )
    graph.add_edge("aryabhata_fix", "chanakya_review")
    return graph.compile()

patchwise_graph = build_patchwise_graph()
