from __future__ import annotations

from api.ws_manager import websocket_manager


class WebSocketManager:
    async def emit(self, session_id: str, data: dict):
        await websocket_manager.broadcast(session_id, data)

    async def emit_agent_status(self, session_id: str, data: dict):
        await self.emit(
            session_id,
            {
                "type": "agent_status_update",
                "session_id": session_id,
                "chanakya": data.get("chanakya", {}),
                "aryabhata": data.get("aryabhata", {}),
                "negotiation_state": data.get("negotiation_state", "idle"),
            },
        )

    async def emit_negotiation_update(self, session_id: str, data: dict):
        await self.emit(
            session_id,
            {
                "type": "negotiation_update",
                "session_id": session_id,
                **data,
            },
        )

    async def emit_patch_evolution(self, session_id: str, data: dict):
        await self.emit(
            session_id,
            {
                "type": "patch_evolution_update",
                "session_id": session_id,
                "rounds": data.get("rounds", []),
            },
        )

    async def emit_joint_verdict(self, session_id: str, data: dict):
        await self.emit(
            session_id,
            {
                "type": "joint_verdict",
                "session_id": session_id,
                **data,
            },
        )

    async def emit_approval_granted(self, session_id: str, data: dict):
        await self.emit(
            session_id,
            {
                "type": "aryabhata_approval",
                "session_id": session_id,
                **data,
            },
        )

    async def emit_cover_letter_draft(self, session_id: str, data: dict):
        await self.emit(
            session_id,
            {
                "type": "cover_letter_draft",
                "session_id": session_id,
                **data,
            },
        )


websocket_event_manager = WebSocketManager()
