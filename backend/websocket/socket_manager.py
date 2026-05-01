"""
WebSocket room isolation per session_id.
"""
from __future__ import annotations

import logging

import socketio

logger = logging.getLogger(__name__)

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    ping_timeout=60,
    ping_interval=25,
    max_http_buffer_size=10_000_000,
)

_session_sockets: dict[str, str] = {}


@sio.event
async def connect(sid, environ, auth):
    session_id = auth.get("session_id") if auth else None
    if not session_id:
        logger.warning("[WS] Connection %s rejected - no session_id", sid)
        return False

    await sio.enter_room(sid, session_id)
    _session_sockets[session_id] = sid
    logger.info("[WS] %s joined room %s", sid, session_id)

    await sio.emit("connected", {"session_id": session_id}, room=session_id)
    return True


@sio.event
async def disconnect(sid):
    for session_id, socket_id in list(_session_sockets.items()):
        if socket_id == sid:
            del _session_sockets[session_id]
            logger.info("[WS] %s left room %s", sid, session_id)
            break


async def emit_to_session(session_id: str, event: str, data: dict):
    """Emit event only to the specific session room."""
    await sio.emit(event, data, room=session_id)


async def emit_agent_token(session_id: str, agent: str, token: str, message_id: str):
    await emit_to_session(
        session_id,
        "agent_token",
        {
            "agent": agent,
            "token": token,
            "message_id": message_id,
        },
    )


async def emit_agent_thinking(session_id: str, agent: str, step: str, detail: str):
    await emit_to_session(
        session_id,
        "agent_thinking",
        {
            "agent": agent,
            "step": step,
            "detail": detail,
        },
    )


async def emit_round_complete(session_id: str, round_number: int, verdict: str, issues: list):
    await emit_to_session(
        session_id,
        "round_complete",
        {
            "round_number": round_number,
            "verdict": verdict,
            "issues": issues,
        },
    )


async def get_active_connections() -> dict:
    return {
        "active_sessions": len(_session_sockets),
        "session_ids": list(_session_sockets.keys()),
    }
