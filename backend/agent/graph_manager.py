"""
Session-scoped LangGraph graph instances.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from langgraph.graph import END, StateGraph

from agent.aryabhata import aryabhata_node
from agent.chanakya import chanakya_node
from agent.interrupt import interrupt_check_node
from agent.state import PatchWiseState

logger = logging.getLogger(__name__)

_graph_instances: dict[str, Any] = {}
_instance_lock = asyncio.Lock()


def _build_graph() -> Any:
    workflow = StateGraph(PatchWiseState)

    workflow.add_node("chanakya", chanakya_node)
    workflow.add_node("aryabhata", aryabhata_node)
    workflow.add_node("interrupt_check", interrupt_check_node)

    workflow.set_entry_point("chanakya")
    workflow.add_edge("chanakya", "interrupt_check")

    workflow.add_conditional_edges(
        "interrupt_check",
        lambda state: state["next"],
        {
            "aryabhata": "aryabhata",
            "end": END,
            "wait": "interrupt_check",
        },
    )

    workflow.add_conditional_edges(
        "aryabhata",
        lambda state: "end"
        if state["verdict"] == "LGTM" or state["round"] >= state["max_rounds"]
        else "chanakya",
        {
            "chanakya": "chanakya",
            "end": END,
        },
    )

    return workflow.compile()


async def get_session_graph(session_id: str):
    """
    Return the isolated graph instance for this session.
    """
    async with _instance_lock:
        if session_id not in _graph_instances:
            _graph_instances[session_id] = _build_graph()
            logger.info("[GraphManager] Created isolated graph for session %s", session_id)
        return _graph_instances[session_id]


async def cleanup_session_graph(session_id: str):
    """Cleanup graph instance after session completion."""
    async with _instance_lock:
        if session_id in _graph_instances:
            del _graph_instances[session_id]
            logger.info("[GraphManager] Cleaned up graph for session %s", session_id)


def get_active_session_count() -> int:
    return len(_graph_instances)
