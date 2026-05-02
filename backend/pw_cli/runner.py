from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any

from app.agents.aryabhata import aryabhata_fix_node_async
from app.agents.chanakya import chanakya_review_node
from core.input_processor import process_input
from pw_cli.protocol import A2AEnvelope
from pw_cli.store import CLISessionStore


@dataclass
class RunResult:
    session_id: str
    status: str
    verdict: str
    current_round: int
    max_rounds: int
    summary: dict[str, Any]


def _safe_state(state: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in state.items():
        if key.startswith("_"):
            continue
        if callable(value):
            continue
        sanitized[key] = value
    return json.loads(json.dumps(sanitized, ensure_ascii=False, default=str))


def _collect_patch_from_path(path: str) -> str:
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    if os.path.isdir(path):
        chunks: list[str] = []
        files = sorted(
            [
                os.path.join(path, name)
                for name in os.listdir(path)
                if name.endswith((".patch", ".diff", ".txt"))
            ]
        )
        for file_path in files:
            with open(file_path, "r", encoding="utf-8", errors="replace") as handle:
                chunks.append(handle.read())
        return "\n\n".join(chunks)
    return path


async def _resolve_input(input_value: str, input_type: str) -> tuple[str, str]:
    if input_type == "file":
        content = _collect_patch_from_path(input_value)
        return ("file", content)
    if input_type == "raw":
        return ("raw", input_value)
    detected, normalized = await process_input(input_value)
    lowered = str(detected).lower()
    if lowered == "file":
        normalized = _collect_patch_from_path(normalized)
    return (lowered, normalized)


def _initial_state(
    session_id: str,
    patch_text: str,
    subsystem: str,
    source_path: str,
    llm_provider: str,
    llm_model: str,
    max_rounds: int,
) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "patch_input": patch_text,
        "kernel_version": "unknown",
        "subsystem": subsystem or "audio",
        "source_path": source_path or "",
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "max_rounds": int(max_rounds),
        "current_round": 1,
        "review_findings": [],
        "fix_attempts": [],
        "similar_patches": [],
        "current_patch": patch_text,
        "verdict": "PENDING",
        "interrupt_hint": None,
        "conversation_log": [],
        "quality_score": 0.0,
        "messages": [],
        "fix_history": [],
        "previous_round_issues": [],
        "current_fixed_patch": None,
        "touched_lines": [],
        "a2a_messages": [],
        "challenge_timeout": 60,
        "shared_a2a_context": {
            "session_id": session_id,
            "original_patch": patch_text,
            "current_patch": patch_text,
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


def _chanakya_summary(state: dict[str, Any]) -> dict[str, Any]:
    latest = state.get("latest_review") if isinstance(state.get("latest_review"), dict) else {}
    issues = latest.get("issues") if isinstance(latest.get("issues"), list) else []
    return {
        "issues": len(issues),
        "quality_score": state.get("quality_score", 0.0),
        "source": state.get("qgenie_last_source", "unknown"),
        "confidence": state.get("chanakya_confidence", 0),
    }


def _aryabhata_summary(state: dict[str, Any]) -> dict[str, Any]:
    validation = state.get("aryabhata_validation") if isinstance(state.get("aryabhata_validation"), dict) else {}
    blockers = validation.get("blockers") if isinstance(validation.get("blockers"), list) else []
    return {
        "verdict": validation.get("verdict", state.get("verdict", "PENDING")),
        "source": validation.get("source", "unknown"),
        "confidence": validation.get("confidence", 0),
        "blockers": len(blockers),
    }


async def run_new_session(
    store: CLISessionStore,
    *,
    input_value: str,
    input_type: str,
    subsystem: str,
    source_path: str,
    llm_provider: str,
    llm_model: str,
    max_rounds: int,
) -> RunResult:
    resolved_type, patch_text = await _resolve_input(input_value, input_type)
    bootstrap_state = _initial_state(
        session_id="bootstrap",
        patch_text=patch_text,
        subsystem=subsystem,
        source_path=source_path,
        llm_provider=llm_provider,
        llm_model=llm_model,
        max_rounds=max_rounds,
    )
    session_id = store.create_session(
        input_type=resolved_type,
        input_ref=input_value[:400],
        subsystem=subsystem or "audio",
        max_rounds=max_rounds,
        state_json=_safe_state(bootstrap_state),
    )
    state = _initial_state(
        session_id=session_id,
        patch_text=patch_text,
        subsystem=subsystem,
        source_path=source_path,
        llm_provider=llm_provider,
        llm_model=llm_model,
        max_rounds=max_rounds,
    )
    return await run_existing_state(store, session_id=session_id, state=state)


async def run_existing_state(store: CLISessionStore, *, session_id: str, state: dict[str, Any]) -> RunResult:
    def _stream_callback(payload: dict[str, Any]) -> None:
        envelope = A2AEnvelope.from_agent_payload(session_id, payload)
        store.append_message(envelope)

    state["_stream_callback"] = _stream_callback
    max_rounds = int(state.get("max_rounds", 5) or 5)

    while True:
        round_before = int(state.get("current_round", 1) or 1)
        if round_before > max_rounds:
            break

        state = await chanakya_review_node(state)
        c_summary = _chanakya_summary(state)
        store.append_round(
            session_id=session_id,
            round_num=round_before,
            phase="chanakya",
            summary=c_summary,
            state_json=_safe_state(state),
        )
        store.update_session(
            session_id,
            current_round=int(state.get("current_round", round_before)),
            verdict=str(state.get("verdict", "PENDING")),
            summary={"phase": "chanakya", **c_summary},
            state_json=_safe_state(state),
        )

        if state.get("verdict") == "LGTM":
            break

        state = await aryabhata_fix_node_async(state)
        a_summary = _aryabhata_summary(state)
        store.append_round(
            session_id=session_id,
            round_num=round_before,
            phase="aryabhata",
            summary=a_summary,
            state_json=_safe_state(state),
        )
        store.update_session(
            session_id,
            current_round=int(state.get("current_round", round_before)),
            verdict=str(state.get("verdict", "PENDING")),
            summary={"phase": "aryabhata", **a_summary},
            state_json=_safe_state(state),
        )

        if state.get("verdict") == "LGTM":
            break
        if round_before >= max_rounds:
            break
        next_round = int(state.get("current_round", round_before) or round_before)
        if next_round <= round_before:
            break

    if state.get("verdict") == "PENDING":
        state["verdict"] = "NEEDS_WORK"

    summary = {
        "conversation_entries": len(state.get("conversation_log") or []),
        "review_rounds": len(state.get("review_findings") or []),
        "fix_rounds": len(state.get("fix_attempts") or []),
        "quality_score": state.get("quality_score", 0.0),
    }
    store.update_session(
        session_id,
        status="completed",
        current_round=int(state.get("current_round", 1) or 1),
        verdict=str(state.get("verdict", "NEEDS_WORK")),
        summary=summary,
        state_json=_safe_state(state),
    )
    return RunResult(
        session_id=session_id,
        status="completed",
        verdict=str(state.get("verdict", "NEEDS_WORK")),
        current_round=int(state.get("current_round", 1) or 1),
        max_rounds=int(state.get("max_rounds", 5) or 5),
        summary=summary,
    )


def run_new_session_sync(store: CLISessionStore, **kwargs: Any) -> RunResult:
    return asyncio.run(run_new_session(store, **kwargs))


def resume_session_sync(store: CLISessionStore, session_id: str) -> RunResult:
    session = store.get_session(session_id)
    if not session:
        raise ValueError(f"Session not found: {session_id}")
    state = dict(session.state_json or {})
    if not state:
        raise ValueError(f"Session {session_id} has no resumable state")
    state["session_id"] = session_id
    if session.status == "completed":
        return RunResult(
            session_id=session_id,
            status=session.status,
            verdict=session.verdict,
            current_round=session.current_round,
            max_rounds=session.max_rounds,
            summary=session.summary,
        )
    return asyncio.run(run_existing_state(store, session_id=session_id, state=state))

