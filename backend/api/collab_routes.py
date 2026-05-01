from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.collaboration_manager import CollabRole, collab_manager

router = APIRouter(prefix="/api/collab", tags=["collaboration"])


class ShareLinkRequest(BaseModel):
    session_id: str
    owner_id: str
    role: CollabRole = CollabRole.CO_REVIEWER
    password: Optional[str] = None
    expiry_hours: int = 24


class JoinSessionRequest(BaseModel):
    share_token: str
    user_id: str
    username: str
    password: Optional[str] = None


class HumanCommentRequest(BaseModel):
    session_id: str
    user_id: str
    username: str
    message_ref: str
    comment: str
    role: CollabRole


class RaiseHandRequest(BaseModel):
    session_id: str
    user_id: str
    username: str
    message_ref: str


class PinMessageRequest(BaseModel):
    session_id: str
    message_ref: str
    pinned_by: str
    note: Optional[str] = ""


@router.post("/share")
async def create_share_link(req: ShareLinkRequest):
    return collab_manager.create_share_link(
        req.session_id,
        req.owner_id,
        req.role,
        req.password,
        req.expiry_hours,
    )


@router.post("/join")
async def join_session(req: JoinSessionRequest):
    try:
        return await collab_manager.join_session(
            req.share_token,
            req.user_id,
            req.username,
            req.password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/comment")
async def add_comment(req: HumanCommentRequest):
    return await collab_manager.add_human_comment(
        req.session_id,
        req.user_id,
        req.username,
        req.message_ref,
        req.comment,
        req.role,
    )


@router.post("/raise-hand")
async def raise_hand(req: RaiseHandRequest):
    await collab_manager.raise_hand(
        req.session_id,
        req.user_id,
        req.username,
        req.message_ref,
    )
    return {"status": "raised"}


@router.post("/pin")
async def pin_message(req: PinMessageRequest):
    return await collab_manager.pin_message(
        req.session_id,
        req.message_ref,
        req.pinned_by,
        req.note or "",
    )


@router.get("/participants/{session_id}")
async def get_participants(session_id: str):
    collab = collab_manager.sessions_by_id.get(session_id)
    if not collab:
        return {"participants": [], "count": 0}

    active = [
        {
            "username": participant.username,
            "role": participant.role.value,
            "joined_at": participant.joined_at.isoformat(),
        }
        for participant in collab.participants.values()
    ]
    return {"participants": active, "count": len(active)}
