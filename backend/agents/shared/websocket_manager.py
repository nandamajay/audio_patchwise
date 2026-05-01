from __future__ import annotations

from typing import Any

from app.runtime import connection_manager


async def stream_agent_message(session_id: str, agent: str, msg_type: str, content: Any):
    payload = {
        "agent": agent,
        "type": msg_type,
        "round": 0,
        "content": content if isinstance(content, str) else "",
        "metadata": content if isinstance(content, dict) else {},
    }
    await connection_manager.broadcast(session_id, payload)
