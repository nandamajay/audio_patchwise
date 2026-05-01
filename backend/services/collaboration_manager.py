from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from database import get_db
from websocket_manager import ws_manager


class CollabRole(str, Enum):
    OWNER = "owner"
    CO_REVIEWER = "co_reviewer"
    OBSERVER = "observer"


@dataclass
class CollabParticipant:
    user_id: str
    username: str
    role: CollabRole
    joined_at: datetime
    is_active: bool = True
    cursor_pos: Optional[str] = None


@dataclass
class CollabSession:
    session_id: str
    share_token: str
    owner_id: str
    participants: dict[str, CollabParticipant] = field(default_factory=dict)
    human_comments: list = field(default_factory=list)
    raised_hands: set[str] = field(default_factory=set)
    pinned_messages: list = field(default_factory=list)
    expires_at: Optional[datetime] = None
    password_hash: Optional[str] = None
    is_active: bool = True


class CollaborationManager:
    def __init__(self):
        self.sessions_by_token: dict[str, CollabSession] = {}
        self.sessions_by_id: dict[str, CollabSession] = {}

    def create_share_link(
        self,
        session_id: str,
        owner_id: str,
        role: CollabRole = CollabRole.CO_REVIEWER,
        password: str | None = None,
        expiry_hours: int = 24,
    ) -> dict:
        """Generate shareable session link."""
        share_token = str(uuid.uuid4())[:12]
        collab = CollabSession(
            session_id=session_id,
            share_token=share_token,
            owner_id=owner_id,
            expires_at=datetime.utcnow() + timedelta(hours=expiry_hours) if expiry_hours else None,
            password_hash=password,
        )
        self.sessions_by_token[share_token] = collab
        self.sessions_by_id[session_id] = collab

        db = next(get_db())
        db.execute(
            """
            INSERT OR REPLACE INTO collab_sessions
            (session_id, share_token, owner_id, role, expires_at, password_hash)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                share_token,
                owner_id,
                role.value,
                collab.expires_at.isoformat() if collab.expires_at else None,
                password,
            ),
        )
        db.commit()

        base_url = "http://localhost:7000"
        share_link = f"{base_url}/session/{session_id}?token={share_token}&role={role.value}"
        return {
            "share_link": share_link,
            "share_token": share_token,
            "role": role.value,
            "expires_at": collab.expires_at.isoformat() if collab.expires_at else "permanent",
        }

    async def join_session(
        self,
        share_token: str,
        user_id: str,
        username: str,
        password: str | None = None,
    ) -> dict:
        """Join collaborative session by share token."""
        collab = self.sessions_by_token.get(share_token)
        if not collab:
            db = next(get_db())
            row = db.execute(
                "SELECT * FROM collab_sessions WHERE share_token=?",
                (share_token,),
            ).fetchone()
            if not row:
                raise ValueError("Invalid or expired share link")

            collab = CollabSession(
                session_id=row["session_id"],
                share_token=row["share_token"],
                owner_id=row["owner_id"],
                expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
                password_hash=row["password_hash"],
            )
            self.sessions_by_token[share_token] = collab
            self.sessions_by_id[collab.session_id] = collab

        if collab.password_hash and password and collab.password_hash != password:
            raise ValueError("Invalid share password")

        participant = CollabParticipant(
            user_id=user_id,
            username=username,
            role=CollabRole.CO_REVIEWER,
            joined_at=datetime.utcnow(),
        )
        collab.participants[user_id] = participant

        await ws_manager.emit_to_session(
            collab.session_id,
            "participant_joined",
            {
                "username": username,
                "role": participant.role.value,
                "message": f"{username} joined as {participant.role.value}",
            },
        )

        return {
            "session_id": collab.session_id,
            "role": participant.role.value,
            "participants": len(collab.participants),
        }

    async def add_human_comment(
        self,
        session_id: str,
        user_id: str,
        username: str,
        message_ref: str,
        comment: str,
        role: CollabRole,
    ):
        """Add a human comment in session thread."""
        comment_obj = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "username": username,
            "message_ref": message_ref,
            "comment": comment,
            "timestamp": datetime.utcnow().isoformat(),
            "role": role.value,
        }

        db = next(get_db())
        db.execute(
            """
            INSERT INTO collab_comments
            (id, session_id, user_id, username, message_ref, comment, role)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                comment_obj["id"],
                session_id,
                user_id,
                username,
                message_ref,
                comment,
                role.value,
            ),
        )
        db.commit()

        collab = self.sessions_by_id.get(session_id)
        if collab:
            collab.human_comments.append(comment_obj)

        await ws_manager.emit_to_session(session_id, "human_comment", comment_obj)
        return comment_obj

    async def raise_hand(self, session_id: str, user_id: str, username: str, message_ref: str):
        """Raise hand on a specific message for discussion."""
        collab = self.sessions_by_id.get(session_id)
        if collab:
            collab.raised_hands.add(message_ref)

        await ws_manager.emit_to_session(
            session_id,
            "hand_raised",
            {
                "user_id": user_id,
                "username": username,
                "message_ref": message_ref,
                "message": f"{username} wants to discuss this point",
            },
        )

    async def pin_message(self, session_id: str, message_ref: str, pinned_by: str, note: str = ""):
        """Pin an important message."""
        pin = {
            "message_ref": message_ref,
            "pinned_by": pinned_by,
            "note": note,
            "timestamp": datetime.utcnow().isoformat(),
        }

        db = next(get_db())
        db.execute(
            """
            INSERT INTO collab_pins (session_id, message_ref, pinned_by, note)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, message_ref, pinned_by, note),
        )
        db.commit()

        collab = self.sessions_by_id.get(session_id)
        if collab:
            collab.pinned_messages.append(pin)

        await ws_manager.emit_to_session(session_id, "message_pinned", pin)
        return pin

    async def broadcast_presence(self, session_id: str):
        """Broadcast active participant list."""
        collab = self.sessions_by_id.get(session_id)
        if collab:
            active = [
                {"username": participant.username, "role": participant.role.value}
                for participant in collab.participants.values()
                if participant.is_active
            ]
            await ws_manager.emit_to_session(
                session_id,
                "presence_update",
                {"active_participants": active, "count": len(active)},
            )


collab_manager = CollaborationManager()
