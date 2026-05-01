from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.dependencies import session_manager
from api.ws_manager import websocket_manager
from graph.interrupt_handler import interrupt_handler
from graph.orchestrator import run_session_loop
from services.history_manager import history_manager

websocket_router = APIRouter(tags=["websocket"])
_tasks: dict[str, asyncio.Task] = {}


@websocket_router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket_manager.connect(session_id, websocket)
    interrupt_handler.register_session(session_id)

    try:
        while True:
            data = await websocket.receive_json()
            event_type = data.get("type")

            if event_type == "start":
                running = _tasks.get(session_id)
                if running is None or running.done():
                    _tasks[session_id] = asyncio.create_task(run_session_loop(session_id))

            elif event_type == "interrupt":
                hint = (data.get("hint") or "").strip()
                interrupt_handler.send_interrupt(session_id, hint or None)
                session_manager.update_session(session_id, status="interrupted")
                history_manager.increment_interrupt(session_id)
                history_manager.save_message(
                    session_id,
                    "USER",
                    "interrupt",
                    hint or "Session pause requested",
                    metadata={"hint": hint or None},
                )
                await websocket_manager.broadcast(
                    session_id,
                    {
                        "type": "session_paused",
                        "message": "⏸️ Session paused. Agents will acknowledge at next round boundary.",
                        "hint": hint,
                        "agent": "system",
                    },
                )

            elif event_type == "resume":
                interrupt_handler.send_resume(session_id)
                session_manager.update_session(session_id, status="running")
                history_manager.save_message(
                    session_id,
                    "SYSTEM",
                    "resume",
                    "Session resumed by user.",
                )
                await websocket_manager.broadcast(
                    session_id,
                    {
                        "type": "session_resumed",
                        "message": "▶️ Session resumed. Agents continuing...",
                        "agent": "system",
                    },
                )

            elif event_type == "abort":
                interrupt_handler.send_abort(session_id)
                session_manager.update_session(
                    session_id,
                    status="interrupted",
                    verdict="USER_ABORTED",
                )
                history_manager.save_message(
                    session_id,
                    "USER",
                    "abort",
                    "Session aborted by user.",
                )
                await websocket_manager.broadcast(
                    session_id,
                    {
                        "type": "session_aborted",
                        "message": "🛑 Session aborted by user.",
                        "agent": "system",
                    },
                )
                break

    except WebSocketDisconnect:
        websocket_manager.disconnect(session_id, websocket)
