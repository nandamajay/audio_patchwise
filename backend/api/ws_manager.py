from __future__ import annotations

from fastapi import WebSocket


class WebSocketManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(session_id, set()).add(websocket)

    def disconnect(self, session_id: str, websocket: WebSocket | None = None) -> None:
        if session_id not in self._connections:
            return
        if websocket is None:
            del self._connections[session_id]
            return
        self._connections[session_id].discard(websocket)
        if not self._connections[session_id]:
            del self._connections[session_id]

    async def broadcast(self, session_id: str, payload: dict) -> None:
        for websocket in list(self._connections.get(session_id, set())):
            try:
                await websocket.send_json(payload)
            except Exception:
                self.disconnect(session_id, websocket)


websocket_manager = WebSocketManager()
