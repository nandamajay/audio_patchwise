from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.agents.llm_bridge import parse_provider_model
from app.models.session import SessionResponse, SessionStartRequest
from app.runtime import SESSION_STORE

try:
    from api.dependencies import session_manager
except Exception:  # pragma: no cover
    session_manager = None

router = APIRouter(prefix="/session", tags=["session"])


def _sanitize_state(payload: dict) -> dict:
    return {key: value for key, value in payload.items() if not callable(value)}


@router.post("/start", response_model=SessionResponse)
def start_session(payload: SessionStartRequest) -> SessionResponse:
    llm_provider, llm_model = parse_provider_model(payload.llm_provider, payload.llm_model)

    if session_manager:
        session_id = session_manager.create_session(
            patch_input={"raw_text": "", "file_path": "", "gerrit_url": "", "lkml_url": ""},
            context={
                "kernel_version": payload.kernel_version,
                "subsystem": payload.subsystem,
                "source_path": payload.source_path,
            },
            config={
                "max_rounds": payload.max_rounds,
                "llm_provider": llm_provider,
                "llm_model": llm_model,
                "review_focus": ["style", "logic", "memory", "lkml", "commit"],
                "search_priority": ["lkml", "gerrit", "local"],
            },
        )
    else:
        from uuid import uuid4

        session_id = str(uuid4())

    SESSION_STORE[session_id] = {
        "session_id": session_id,
        "patch_input": "",
        "kernel_version": payload.kernel_version,
        "subsystem": payload.subsystem,
        "source_path": payload.source_path,
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "max_rounds": payload.max_rounds,
        "current_round": 1,
        "review_findings": [],
        "fix_attempts": [],
        "similar_patches": [],
        "current_patch": "",
        "verdict": "PENDING",
        "interrupt_hint": None,
        "conversation_log": [],
        "quality_score": 0.0,
        "messages": [],
        "current_fixed_patch": None,
        "touched_lines": [],
        "a2a_messages": [],
        "challenge_timeout": 60,
        "shared_a2a_context": {
            "session_id": session_id,
            "original_patch": "",
            "current_patch": "",
            "round_number": 1,
            "negotiation_threads": {},
            "all_messages": [],
            "touched_lines": [],
            "impact_radius": {},
            "chanakya_knowledge": {},
            "aryabhata_fix_result": None,
            "user_arbitration_pending": False,
            "lgtm": False,
            "challenge_timeout": 60,
        },
    }
    return SessionResponse(
        session_id=session_id,
        status="created",
        kernel_version=payload.kernel_version,
        subsystem=payload.subsystem,
        source_path=payload.source_path,
        llm_provider=llm_provider,
        llm_model=llm_model,
        max_rounds=payload.max_rounds,
    )


@router.get("/{session_id}")
def get_session(session_id: str) -> dict:
    state = SESSION_STORE.get(session_id)
    if state:
        return _sanitize_state(state)

    if session_manager:
        snapshot = session_manager.get_session(session_id)
        if snapshot:
            return {
                "session_id": snapshot.session_id,
                "status": snapshot.status.value,
                "current_round": snapshot.current_round,
                "max_rounds": snapshot.max_rounds,
                "verdict": snapshot.verdict,
                "conversation": snapshot.conversation,
            }

    if not state:
        raise HTTPException(status_code=404, detail="session not found")
    return state
