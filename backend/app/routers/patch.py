from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.models.patch import PatchResponse, PatchSubmitRequest
from app.runtime import PATCH_STORE, SESSION_STORE

try:
    from api.dependencies import session_manager
except Exception:  # pragma: no cover
    session_manager = None

router = APIRouter(prefix="/patch", tags=["patch"])


@router.post("/submit", response_model=PatchResponse)
def submit_patch(payload: PatchSubmitRequest) -> PatchResponse:
    session_exists = payload.session_id in SESSION_STORE
    snapshot_exists = bool(session_manager and session_manager.get_session(payload.session_id))
    if not session_exists and not snapshot_exists:
        raise HTTPException(status_code=404, detail="session not found")

    patch_id = str(uuid4())
    if payload.session_id in SESSION_STORE:
        SESSION_STORE[payload.session_id]["patch_input"] = payload.patch_input
        SESSION_STORE[payload.session_id]["current_patch"] = payload.patch_input

    if session_manager:
        session_manager.update_session(
            payload.session_id,
            patch_input={
                "raw_text": payload.patch_input,
                "file_path": "",
                "gerrit_url": "",
                "lkml_url": "",
            },
            status="running",
        )

    PATCH_STORE[patch_id] = {
        "patch_id": patch_id,
        "session_id": payload.session_id,
        "status": "submitted",
        "patch_input": payload.patch_input,
    }
    return PatchResponse(
        patch_id=patch_id,
        session_id=payload.session_id,
        status="submitted",
        current_patch=payload.patch_input,
    )


@router.get("/{patch_id}")
def get_patch(patch_id: str) -> dict:
    patch = PATCH_STORE.get(patch_id)
    if not patch:
        raise HTTPException(status_code=404, detail="patch not found")
    return patch
