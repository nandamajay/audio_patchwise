from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.agents.graph import patchwise_graph
from app.knowledge.sql_store import PatchSQLStore
from app.knowledge.vector_store import PatchVectorStore
from app.runtime import REPORT_STORE, SESSION_STORE, connection_manager

router = APIRouter(tags=["agents"])
RUN_TASKS: dict[str, asyncio.Task] = {}


def _stream_callback_for(loop: asyncio.AbstractEventLoop, session_id: str):
    def _callback(payload: dict) -> None:
        asyncio.run_coroutine_threadsafe(
            connection_manager.broadcast(session_id, payload),
            loop,
        )

    return _callback


async def run_agent_loop(session_id: str) -> None:
    state = SESSION_STORE.get(session_id)
    if not state:
        return

    loop = asyncio.get_running_loop()
    state["_stream_callback"] = _stream_callback_for(loop, session_id)

    final_state = await asyncio.to_thread(patchwise_graph.invoke, state)
    SESSION_STORE[session_id] = final_state

    try:
        PatchVectorStore(collection_name="patchwise_alsa_asoc").update_from_session(
            final_state
        )
        PatchSQLStore().update_from_session(final_state)
    except Exception:
        # Keep runtime path resilient when optional local DB/vector deps are unavailable.
        pass

    REPORT_STORE[session_id] = {
        "session_id": session_id,
        "verdict": final_state.get("verdict", "PENDING"),
        "quality_score": final_state.get("quality_score", 0.0),
        "rounds": final_state.get("current_round", 1),
        "review_findings": final_state.get("review_findings", []),
        "fix_attempts": final_state.get("fix_attempts", []),
        "similar_patches": final_state.get("similar_patches", []),
    }

    await connection_manager.broadcast(
        session_id,
        {
            "agent": "chanakya",
            "type": "lgtm" if final_state.get("verdict") == "LGTM" else "verdict",
            "round": final_state.get("current_round", 1),
            "content": "✅ LGTM — CHANAKYA approves the patch!"
            if final_state.get("verdict") == "LGTM"
            else "Review loop completed at max rounds.",
            "metadata": {
                "verdict": final_state.get("verdict"),
                "quality_score": final_state.get("quality_score"),
            },
        },
    )


@router.websocket("/ws/agent-stream/{session_id}")
@router.websocket("/ws/{session_id}")
async def agent_stream(websocket: WebSocket, session_id: str) -> None:
    await connection_manager.connect(session_id, websocket)
    try:
        await connection_manager.broadcast(
            session_id,
            {
                "agent": "system",
                "type": "thinking",
                "round": SESSION_STORE.get(session_id, {}).get("current_round", 1),
                "content": "Agent stream connected.",
                "metadata": {},
            },
        )

        if session_id in SESSION_STORE and SESSION_STORE[session_id].get("patch_input"):
            running = RUN_TASKS.get(session_id)
            if running is None or running.done():
                RUN_TASKS[session_id] = asyncio.create_task(run_agent_loop(session_id))

        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            if msg_type == "interrupt":
                hint = data.get("hint", "")
                if session_id in SESSION_STORE:
                    SESSION_STORE[session_id]["interrupt_hint"] = hint
                await connection_manager.broadcast(
                    session_id,
                    {
                        "agent": "system",
                        "type": "thinking",
                        "round": SESSION_STORE.get(session_id, {}).get("current_round", 1),
                        "content": "Soft interrupt captured.",
                        "metadata": {"hint": hint},
                    },
                )
            elif msg_type == "start":
                if session_id in SESSION_STORE:
                    running = RUN_TASKS.get(session_id)
                    if running is None or running.done():
                        RUN_TASKS[session_id] = asyncio.create_task(run_agent_loop(session_id))
            else:
                await connection_manager.broadcast(
                    session_id,
                    {
                        "agent": "system",
                        "type": "thinking",
                        "round": SESSION_STORE.get(session_id, {}).get("current_round", 1),
                        "content": "Unsupported message type ignored.",
                        "metadata": {"received": msg_type},
                    },
                )
    except WebSocketDisconnect:
        await connection_manager.disconnect(session_id, websocket)
