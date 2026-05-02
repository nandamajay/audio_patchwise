from __future__ import annotations

import asyncio
from dataclasses import asdict
from uuid import uuid4

from pydantic import BaseModel

from core.input_processor import process_input, detect_input_type

from fastapi import APIRouter, HTTPException

from api.dependencies import session_manager
from app.runtime import SESSION_STORE

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("")
@router.get("/")
async def list_sessions(limit: int = 50):
    sessions = session_manager.get_all_sessions(limit=limit)
    return sessions


class PatchInputRequest(BaseModel):
    input_type: str
    content: str
    kernel_path: str | None = None
    subsystem: str | None = None
    llm_provider: str | None = "qgenie"
    llm_model: str | None = "gpt-4o"
    max_rounds: int | None = 5


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

    # Compatibility path: when kernel_path/subsystem are supplied, start a real session.
    if payload.kernel_path or payload.subsystem:
        if session_manager:
            session_id = session_manager.create_session(
                patch_input={"raw_text": content, "file_path": "", "gerrit_url": "", "lkml_url": ""},
                context={
                    "kernel_version": "unknown",
                    "subsystem": payload.subsystem or "audio",
                    "source_path": payload.kernel_path or "",
                },
                config={
                    "max_rounds": int(payload.max_rounds or 5),
                    "llm_provider": payload.llm_provider or "qgenie",
                    "llm_model": payload.llm_model or "gpt-4o",
                    "review_focus": ["style", "logic", "memory", "lkml", "commit"],
                    "search_priority": ["lkml", "gerrit", "local"],
                },
            )
        else:
            session_id = str(uuid4())

        SESSION_STORE[session_id] = {
            "session_id": session_id,
            "patch_input": content,
            "kernel_version": "unknown",
            "subsystem": payload.subsystem or "audio",
            "source_path": payload.kernel_path or "",
            "llm_provider": payload.llm_provider or "qgenie",
            "llm_model": payload.llm_model or "gpt-4o",
            "max_rounds": int(payload.max_rounds or 5),
            "current_round": 1,
            "review_findings": [],
            "fix_attempts": [],
            "similar_patches": [],
            "current_patch": content,
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
                "original_patch": content,
                "current_patch": content,
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

        try:
            from app.routers.agents import RUN_TASKS, run_agent_loop

            RUN_TASKS[session_id] = asyncio.create_task(run_agent_loop(session_id))
        except Exception:
            pass

        return {
            "session_id": session_id,
            "status": "started",
            "input_type": input_type,
            "fetching": fetching,
            "content": content,
        }

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
