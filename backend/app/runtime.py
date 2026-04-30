from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket

SESSION_STORE: dict[str, dict[str, Any]] = {}
PATCH_STORE: dict[str, dict[str, Any]] = {}
REPORT_STORE: dict[str, dict[str, Any]] = {}


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.setdefault(session_id, set()).add(websocket)

    async def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            if session_id in self._connections:
                self._connections[session_id].discard(websocket)
                if not self._connections[session_id]:
                    del self._connections[session_id]

    async def broadcast(self, session_id: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            targets = list(self._connections.get(session_id, set()))
        stale: list[WebSocket] = []
        for websocket in targets:
            try:
                await websocket.send_json(payload)
            except Exception:
                stale.append(websocket)
        for websocket in stale:
            await self.disconnect(session_id, websocket)


connection_manager = ConnectionManager()
