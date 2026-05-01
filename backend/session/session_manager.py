from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from knowledge.sqlite_store import SQLiteStore
from app.runtime import connection_manager


class SessionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    FAILED = "failed"
    SUBMITTED = "submitted"


@dataclass
class SessionSnapshot:
    session_id: str
    status: SessionStatus
    created_at: str
    updated_at: str
    patch_input: dict
    context: dict
    config: dict
    current_round: int
    max_rounds: int
    conversation: list
    issues_found: list
    final_patch: Optional[str]
    review_report: Optional[dict]
    verdict: Optional[str]
    submission: Optional[dict]


class SessionManager:
    _emitted_events: Dict[str, set] = {}

    def __init__(self, db: SQLiteStore):
        self.db = db
        self.sio = None

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_session(self, patch_input: dict, context: dict, config: dict) -> str:
        session_id = str(uuid.uuid4())
        snapshot = SessionSnapshot(
            session_id=session_id,
            status=SessionStatus.PENDING,
            created_at=self._now(),
            updated_at=self._now(),
            patch_input=patch_input,
            context=context,
            config=config,
            current_round=0,
            max_rounds=config.get("max_rounds", 5),
            conversation=[],
            issues_found=[],
            final_patch=None,
            review_report=None,
            verdict=None,
            submission=None,
        )
        payload = asdict(snapshot)
        payload["status"] = snapshot.status.value
        self.db.save_session(payload)
        return session_id

    def get_session(self, session_id: str) -> Optional[SessionSnapshot]:
        data = self.db.get_session(session_id)
        if data:
            status_value = data.get("status", SessionStatus.PENDING.value)
            data["status"] = SessionStatus(status_value)
            return SessionSnapshot(**data)
        return None

    def update_session(self, session_id: str, **kwargs) -> None:
        kwargs["updated_at"] = self._now()
        if "status" in kwargs and isinstance(kwargs["status"], SessionStatus):
            kwargs["status"] = kwargs["status"].value
        self.db.update_session(session_id, kwargs)

    def append_message(self, session_id: str, message: dict) -> None:
        session = self.get_session(session_id)
        if session:
            session.conversation.append(message)
            self.update_session(session_id, conversation=session.conversation)

    def get_all_sessions(self, limit: int = 50) -> List[dict]:
        return self.db.list_sessions(limit=limit)

    def resume_session(self, session_id: str) -> Optional[SessionSnapshot]:
        session = self.get_session(session_id)
        if session and session.status == SessionStatus.INTERRUPTED:
            self.update_session(session_id, status=SessionStatus.RUNNING)
            return self.get_session(session_id)
        return None

    def delete_session(self, session_id: str) -> None:
        self.cleanup_session(session_id)
        self.db.delete_session(session_id)

    async def _persist_session_event(self, session_id: str, event_type: str, data: dict) -> None:
        session = self.get_session(session_id)
        if not session:
            return
        event = {
            "event_type": event_type,
            "data": data,
            "timestamp": self._now(),
        }
        history = list(session.context.get("events", []))
        history.append(event)
        self.update_session(session_id, context={**session.context, "events": history[-200:]})

    async def broadcast_session_update(self, session_id, event_type, data):
        # Dedup: only emit each round event once
        if event_type in ("round_complete", "max_rounds_reached", "lgtm"):
            if session_id not in self._emitted_events:
                self._emitted_events[session_id] = set()
            key = f'{event_type}_{data.get("round",0)}'
            if key in self._emitted_events[session_id]:
                return
            self._emitted_events[session_id].add(key)

        if self.sio is not None:
            await self.sio.emit(event_type, data, room=session_id)
        else:
            await connection_manager.broadcast(
                session_id,
                {
                    "agent": "system",
                    "type": event_type,
                    "round": data.get("round", 0),
                    "content": data.get("message", ""),
                    "metadata": data,
                },
            )

        if event_type in ("round_complete", "lgtm", "max_rounds_reached", "session_started"):
            await self._persist_session_event(session_id, event_type, data)

    def cleanup_session(self, session_id):
        self._emitted_events.pop(session_id, None)
