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
    if state["verdict"] == "LGTM":
        return "end"
    if state["current_round"] >= state["max_rounds"]:
        return "end"
    return "aryabhata_fix"

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
