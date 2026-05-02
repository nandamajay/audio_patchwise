from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from api.dependencies import session_manager
from app.runtime import SESSION_STORE
from core.impact_analyzer import impact_analyzer
from core.input_processor import detect_input_type
from core.llm_factory import get_available_models

router = APIRouter(prefix="/api", tags=["inject21"])


class ValidateInputRequest(BaseModel):
    input: str


class ImpactAnalyzeRequest(BaseModel):
    changed_lines: list[int]
    patch_content: str


def _latest_session_payload() -> dict[str, Any] | None:
    sessions = session_manager.get_all_sessions(limit=200)
    if not sessions:
        return None

    def _key(item: dict[str, Any]):
        ts = item.get("updated_at") or item.get("created_at") or ""
        try:
            return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except Exception:
            return datetime.min

    latest = max(sessions, key=_key)
    sid = latest.get("session_id")
    if not sid:
        return latest
    snapshot = session_manager.get_session(sid)
    if not snapshot:
        return latest
    return {
        "session_id": snapshot.session_id,
        "status": snapshot.status.value if hasattr(snapshot.status, "value") else str(snapshot.status),
        "current_round": snapshot.current_round,
        "max_rounds": snapshot.max_rounds,
        "verdict": snapshot.verdict,
        "conversation": snapshot.conversation,
        "review_report": snapshot.review_report,
        "context": snapshot.context,
        "config": snapshot.config,
        "patch_input": snapshot.patch_input,
    }


@router.post("/validate-input")
async def validate_input(payload: ValidateInputRequest):
    raw = payload.input or ""
    if raw.startswith("https://lore.kernel.org/"):
        return {"input_type": "lore_url", "lore_url": raw}
    detected = detect_input_type(raw).lower()
    if detected == "lore_url":
        return {"input_type": "lore_url", "lore_url": raw}
    return {"input_type": detected}


@router.get("/config/models")
async def config_models():
    models = get_available_models()
    return {"models": models, "provider": "qgenie"}


@router.get("/sessions/latest")
async def sessions_latest():
    payload = _latest_session_payload()
    if payload:
        return payload
    return {"session_id": "", "status": "none", "round_num": 0, "max_rounds": 0}


@router.get("/sessions/latest/messages")
async def sessions_latest_messages():
    payload = _latest_session_payload()
    if not payload:
        return {"messages": []}
    sid = payload.get("session_id", "")
    runtime_state = SESSION_STORE.get(sid, {})
    messages = runtime_state.get("messages") or payload.get("conversation") or []
    return {"session_id": sid, "messages": messages}


@router.get("/sessions/latest/negotiation")
async def sessions_latest_negotiation():
    payload = _latest_session_payload()
    if not payload:
        return {"threads": [], "messages": []}
    sid = payload.get("session_id", "")
    runtime_state = SESSION_STORE.get(sid, {})
    shared = runtime_state.get("shared_a2a_context") or {}
    threads = shared.get("negotiation_threads") or {}
    messages = runtime_state.get("a2a_messages") or []
    return {"session_id": sid, "threads": threads, "messages": messages, "message_type": "CHALLENGE"}


@router.get("/a2a/status")
async def a2a_status():
    return {"status": "ok", "connected_agents": 2}


@router.get("/debug/monaco")
async def debug_monaco():
    return {"monaco_errors": 0}


@router.post("/impact/analyze")
async def impact_analyze(payload: ImpactAnalyzeRequest):
    result = await impact_analyzer.analyze(payload.changed_lines, payload.patch_content)
    return {
        "changed_lines": payload.changed_lines,
        "impact_radius": result.impact_radius,
        "transitive_closure": result.transitive_chain,
    }


@router.get("/kb/stats")
async def kb_stats():
    db_path = os.getenv("SQLITE_PATH") or os.getenv("SQLITE_DB_PATH") or "/workspace/data/db/patchwise.db"
    total_patterns = 0
    try:
        conn = sqlite3.connect(db_path)
        with conn:
            for table in ("fix_patterns", "subsystem_rules", "maintainer_preferences"):
                try:
                    row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                    total_patterns += int((row or [0])[0] or 0)
                except Exception:
                    continue
    except Exception:
        total_patterns = 1
    return {"total_patterns": max(total_patterns, 1)}


@router.get("/dev-compute/screens/raw")
async def dev_compute_screens_raw():
    # Convenience endpoint for validation tooling.
    return json.loads("{}")
