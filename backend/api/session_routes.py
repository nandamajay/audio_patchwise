from __future__ import annotations

from dataclasses import asdict

from pydantic import BaseModel

from core.input_processor import process_input, detect_input_type

from fastapi import APIRouter, HTTPException

from api.dependencies import session_manager

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("")
@router.get("/")
async def list_sessions(limit: int = 50):
    sessions = session_manager.get_all_sessions(limit=limit)
    return sessions


class PatchInputRequest(BaseModel):
    input_type: str
    content: str


@router.post("")
async def detect_patch_input(payload: PatchInputRequest):
    detected = detect_input_type(payload.content)
    input_type = detected.lower()
    fetching = detected in {"LORE_URL", "GERRIT_URL"}
    content = payload.content
    if fetching:
        try:
            _dtype, content = await process_input(payload.content)
        except Exception:
            pass
    return {"input_type": input_type, "fetching": fetching, "content": content}


@router.get("/{session_id}")
async def get_session(session_id: str):
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    data = asdict(session)
    data["status"] = session.status.value
    return data


@router.post("/{session_id}/resume")
async def resume_session(session_id: str):
    session = session_manager.resume_session(session_id)
    if not session:
        raise HTTPException(status_code=400, detail="Session cannot be resumed")
    return {"status": "resumed", "session_id": session_id}


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    session_manager.delete_session(session_id)
    return {"status": "deleted"}
