from __future__ import annotations

from api.ws_manager import websocket_manager


class WebSocketManagerAdapter:
    async def emit_to_session(self, session_id: str, event: str, data: dict):
        payload = {"event": event, **(data or {})}
        await websocket_manager.broadcast(session_id, payload)


ws_manager = WebSocketManagerAdapter()
