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


# True A2A event schemas used by frontend hook consumers.
EVENT_SCHEMAS = {
    "a2a_message": {
        "sender": str,
        "receiver": str,
        "type": str,
        "content": str,
        "metadata": dict,
        "issue_id": str,
        "round": int,
        "confidence": float,
        "message_id": str,
        "timestamp": str,
    },
    "impact_map_update": {
        "session_id": str,
        "touched_lines": list,
        "impact_radius": {
            "direct": list,
            "downstream": list,
            "upstream": list,
            "cross_file": list,
            "impact_chain": list,
        },
    },
    "arbitration_required": {
        "session_id": str,
        "issue_id": str,
        "chanakya_position": str,
        "aryabhata_position": str,
        "evidence_summary": dict,
    },
    "surgical_review_start": {
        "session_id": str,
        "scope_lines": list,
        "scope_reason": str,
        "round": int,
    },
}
