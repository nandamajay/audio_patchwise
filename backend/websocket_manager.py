"""
WebSocket event helper for True A2A UI events.
"""

from __future__ import annotations

from typing import Any

from app.runtime import connection_manager


class WebSocketEventManager:
    async def emit_to_session(
        self,
        session_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        """
        Emit typed event envelopes for frontend consumers.
        """
        await connection_manager.broadcast(
            session_id,
            {
                "agent": "system",
                "type": event_type,
                "round": payload.get("round", 0),
                "content": payload.get("content", ""),
                "metadata": payload,
            },
        )


websocket_manager = WebSocketEventManager()
