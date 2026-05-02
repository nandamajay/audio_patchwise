from __future__ import annotations

import asyncio
import hashlib
import json
import os
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from app.agents.aryabhata import aryabhata_fix_node_async
from app.agents.chanakya import chanakya_review_node
from pw_cli.input_adapter import InputBundle, resolve_input_bundle
from pw_cli.protocol import A2AEnvelope, MessageType
from pw_cli.store import CLISessionStore


@dataclass
class RunResult:
    session_id: str
    status: str
    verdict: str
    current_round: int
    max_rounds: int
    summary: dict[str, Any]


ProgressCallback = Optional[Callable[[dict[str, Any]], None]]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bool_env(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, str(default))).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip() or default)
    except Exception:
        return int(default)


def _safe_state(state: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in state.items():
        if key.startswith("_"):
            continue
        if callable(value):
            continue
        sanitized[key] = value
    return json.loads(json.dumps(sanitized, ensure_ascii=False, default=str))


def _truncate_value(value: Any, *, depth: int = 0, max_depth: int = 5, max_str: int = 1200, max_list: int = 25) -> Any:
    if depth >= max_depth:
        return "<truncated>"
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        if len(value) <= max_str:
            return value
        trimmed = len(value) - max_str
        return f"{value[:max_str]} ...<trimmed {trimmed} chars>"
    if isinstance(value, list):
        clipped = [_truncate_value(item, depth=depth + 1, max_depth=max_depth, max_str=max_str, max_list=max_list) for item in value[:max_list]]
        if len(value) > max_list:
            clipped.append(f"<trimmed {len(value) - max_list} items>")
        return clipped
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for idx, (k, v) in enumerate(value.items()):
            if idx >= 60:
                output["__trimmed_keys__"] = len(value) - 60
                break
            output[str(k)] = _truncate_value(v, depth=depth + 1, max_depth=max_depth, max_str=max_str, max_list=max_list)
        return output
    return str(value)


def _compact_round_state(state: dict[str, Any]) -> dict[str, Any]:
    safe = _safe_state(state)
    patch_input = str(safe.pop("patch_input", "") or "")
    current_patch = str(safe.pop("current_patch", "") or "")
    current_fixed_patch = str(safe.pop("current_fixed_patch", "") or "")
    conversation_log = safe.pop("conversation_log", [])
    review_findings = safe.get("review_findings")
    fix_attempts = safe.get("fix_attempts")
    similar_patches = safe.get("similar_patches")

    if isinstance(safe.get("latest_review"), dict):
        latest = safe.get("latest_review", {})
        issues = latest.get("issues") if isinstance(latest.get("issues"), list) else []
        safe["latest_review"] = {
            "round": latest.get("round"),
            "summary": latest.get("summary"),
            "issue_count": len(issues),
            "quality_score": latest.get("quality_score"),
            "analysis_mode": latest.get("analysis_mode"),
            "patchwise": latest.get("patchwise"),
        }

    safe["snapshot_meta"] = {
        "compact": True,
        "patch_input_len": len(patch_input),
        "current_patch_len": len(current_patch),
        "current_fixed_patch_len": len(current_fixed_patch),
        "patch_input_sha": hashlib.sha1(patch_input.encode("utf-8", errors="ignore")).hexdigest()[:12] if patch_input else "",
        "current_patch_sha": hashlib.sha1(current_patch.encode("utf-8", errors="ignore")).hexdigest()[:12] if current_patch else "",
        "current_fixed_patch_sha": hashlib.sha1(current_fixed_patch.encode("utf-8", errors="ignore")).hexdigest()[:12] if current_fixed_patch else "",
        "conversation_entries": len(conversation_log) if isinstance(conversation_log, list) else 0,
        "review_rounds": len(review_findings) if isinstance(review_findings, list) else 0,
        "fix_rounds": len(fix_attempts) if isinstance(fix_attempts, list) else 0,
        "similar_refs": len(similar_patches) if isinstance(similar_patches, list) else 0,
    }
    safe["conversation_log_count"] = len(conversation_log) if isinstance(conversation_log, list) else 0
    safe["compact_snapshot"] = True

    max_str = max(300, _int_env("PW_CLI_ROUND_SNAPSHOT_MAX_STR", 1200))
    max_list = max(5, _int_env("PW_CLI_ROUND_SNAPSHOT_MAX_LIST", 25))
    return _truncate_value(safe, max_str=max_str, max_list=max_list)


def _round_state_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    if _bool_env("PW_CLI_FULL_ROUND_STATE", False):
        return _safe_state(state)
    return _compact_round_state(state)


def _ensure_shared_context(state: dict[str, Any]) -> dict[str, Any]:
    shared = state.get("shared_a2a_context")
    if not isinstance(shared, dict):
        shared = {}
    state["shared_a2a_context"] = shared
    return shared


def _is_waiting_for_user(state: dict[str, Any]) -> bool:
    shared = _ensure_shared_context(state)
    if bool(shared.get("user_arbitration_pending")):
        return True
    return str(state.get("verdict", "")).upper() == "BLOCKED"


def _build_waiting_payload(state: dict[str, Any], round_num: int) -> dict[str, Any]:
    validation = state.get("aryabhata_validation") if isinstance(state.get("aryabhata_validation"), dict) else {}
    blockers = validation.get("blockers") if isinstance(validation.get("blockers"), list) else []
    confidence = int(validation.get("confidence", 0) or 0)
    hard_reason = state.get("hard_block_reason") if isinstance(state.get("hard_block_reason"), dict) else {}
    reason = str(hard_reason.get("reason") or "arbitration_required")
    if not blockers:
        blockers = ["ARYABHATA requested user clarification before continuing."]
    question = (
        "ARYABHATA raised strong evidence blockers. "
        "Provide clarification or run override to force a decision."
    )
    return {
        "round": int(round_num),
        "reason": reason,
        "confidence": confidence,
        "blockers": blockers[:12],
        "question": question,
    }


def _waiting_summary(state: dict[str, Any], waiting_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "phase": "user_arbitration",
        "reason": waiting_payload.get("reason", "arbitration_required"),
        "question": waiting_payload.get("question", ""),
        "blocker_count": len(waiting_payload.get("blockers") or []),
        "confidence": waiting_payload.get("confidence", 0),
        "current_round": int(state.get("current_round", 1) or 1),
    }


def _final_summary(state: dict[str, Any], kb_patterns: list[dict[str, Any]], learning: dict[str, Any]) -> dict[str, Any]:
    return {
        "conversation_entries": len(state.get("conversation_log") or []),
        "review_rounds": len(state.get("review_findings") or []),
        "fix_rounds": len(state.get("fix_attempts") or []),
        "quality_score": state.get("quality_score", 0.0),
        "input_type": state.get("input_type", "raw"),
        "input_history_found": bool(
            ((state.get("input_metadata") or {}).get("history") or {}).get("found")
            if isinstance(state.get("input_metadata"), dict)
            else False
        ),
        "kb_active_patterns": len(kb_patterns),
        "kb_learning": learning,
    }


def _user_response_message_type(mode: str) -> MessageType:
    mode = str(mode or "").lower()
    if mode in {"clarify", "respond"}:
        return MessageType.CLARIFICATION_RESPONSE
    if mode == "override":
        return MessageType.APPROVE
    return MessageType.RESPONSE


def _emit_progress(callback: ProgressCallback, payload: dict[str, Any]) -> None:
    if not callable(callback):
        return
    try:
        callback(payload)
    except Exception:
        # Progress reporting must never break the review flow.
        pass


def _run_coro_sync(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    except KeyboardInterrupt:
        pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            with suppress(Exception):
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        raise
    finally:
        with suppress(Exception):
            loop.run_until_complete(loop.shutdown_asyncgens())
        with suppress(Exception):
            loop.run_until_complete(loop.shutdown_default_executor())
        asyncio.set_event_loop(None)
        with suppress(Exception):
            loop.close()


def _initial_state(
    session_id: str,
    patch_text: str,
    subsystem: str,
    source_path: str,
    input_bundle: InputBundle,
    llm_provider: str,
    llm_model: str,
    max_rounds: int,
) -> dict[str, Any]:
    lore_url = input_bundle.input_ref if input_bundle.input_type == "lore_url" else ""
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
        "input_type": input_bundle.input_type,
        "input_url": lore_url,
        "lore_url": lore_url,
        "input_metadata": input_bundle.metadata,
        "input_evidence": input_bundle.evidence,
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
            "input_metadata": input_bundle.metadata,
            "input_evidence": input_bundle.evidence,
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
    progress_callback: ProgressCallback = None,
) -> RunResult:
    bundle = await resolve_input_bundle(input_value, input_type, subsystem=subsystem)
    patch_text = bundle.patch_text
    bootstrap_state = _initial_state(
        session_id="bootstrap",
        patch_text=patch_text,
        subsystem=subsystem,
        source_path=source_path,
        input_bundle=bundle,
        llm_provider=llm_provider,
        llm_model=llm_model,
        max_rounds=max_rounds,
    )
    session_id = store.create_session(
        input_type=bundle.input_type,
        input_ref=bundle.input_ref[:400],
        subsystem=subsystem or "audio",
        max_rounds=max_rounds,
        state_json=_safe_state(bootstrap_state),
    )
    _emit_progress(
        progress_callback,
        {
            "type": "session_created",
            "session_id": session_id,
            "status": "running",
            "round": 1,
            "max_rounds": int(max_rounds),
            "timestamp": _utc_now(),
        },
    )
    state = _initial_state(
        session_id=session_id,
        patch_text=patch_text,
        subsystem=subsystem,
        source_path=source_path,
        input_bundle=bundle,
        llm_provider=llm_provider,
        llm_model=llm_model,
        max_rounds=max_rounds,
    )
    return await run_existing_state(
        store,
        session_id=session_id,
        state=state,
        progress_callback=progress_callback,
    )


async def run_existing_state(
    store: CLISessionStore,
    *,
    session_id: str,
    state: dict[str, Any],
    progress_callback: ProgressCallback = None,
) -> RunResult:
    def _stream_callback(payload: dict[str, Any]) -> None:
        envelope = A2AEnvelope.from_agent_payload(session_id, payload)
        store.append_message(envelope)
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        _emit_progress(
            progress_callback,
            {
                "type": "stream",
                "session_id": session_id,
                "round": int(payload.get("round", state.get("current_round", 1)) or 1),
                "agent": payload.get("agent"),
                "message_type": payload.get("type"),
                "task_type": payload.get("task_type"),
                "source": payload.get("source"),
                "content": str(payload.get("content", "") or "")[:220],
                "metadata": {
                    "issue_count": metadata.get("issue_count"),
                    "confidence": metadata.get("confidence"),
                    "blockers": metadata.get("blockers"),
                    "validation_passed": payload.get("validation_passed"),
                },
                "timestamp": _utc_now(),
            },
        )

    state["_stream_callback"] = _stream_callback
    max_rounds = int(state.get("max_rounds", 5) or 5)
    subsystem = str(state.get("subsystem", "audio") or "audio")
    kb_patterns = store.get_active_kb_patterns(subsystem=subsystem, limit=12)
    state["kb_active_patterns"] = kb_patterns
    shared = _ensure_shared_context(state)
    shared["kb_active_patterns"] = kb_patterns
    state["shared_a2a_context"] = shared
    initial_evidence = state.get("input_evidence") if isinstance(state.get("input_evidence"), list) else []
    if initial_evidence:
        store.append_message(
            A2AEnvelope(
                session_id=session_id,
                round_num=0,
                sender="system",
                receiver="chanakya",
                message_type=MessageType.STATUS,
                content="Input evidence loaded for autonomous A2A session",
                evidence={
                    "input_evidence": initial_evidence,
                    "input_metadata": state.get("input_metadata", {}),
                    "kb_active_patterns": kb_patterns,
                },
                confidence_score=1.0,
                source="input_adapter",
                task_type="input_context",
            )
        )

    _emit_progress(
        progress_callback,
        {
            "type": "status",
            "session_id": session_id,
            "status": "running",
            "stage": "a2a_loop_start",
            "round": int(state.get("current_round", 1) or 1),
            "max_rounds": int(state.get("max_rounds", 5) or 5),
            "timestamp": _utc_now(),
        },
    )

    while True:
        round_before = int(state.get("current_round", 1) or 1)
        if round_before > max_rounds:
            break

        _emit_progress(
            progress_callback,
            {
                "type": "phase",
                "session_id": session_id,
                "phase": "chanakya",
                "round": round_before,
                "status": "running",
                "timestamp": _utc_now(),
            },
        )
        state = await chanakya_review_node(state)
        c_summary = _chanakya_summary(state)
        store.append_round(
            session_id=session_id,
            round_num=round_before,
            phase="chanakya",
            summary=c_summary,
            state_json=_round_state_snapshot(state),
        )
        store.update_session(
            session_id,
            current_round=int(state.get("current_round", round_before)),
            verdict=str(state.get("verdict", "PENDING")),
            summary={"phase": "chanakya", **c_summary},
            state_json=_safe_state(state),
        )
        _emit_progress(
            progress_callback,
            {
                "type": "phase_complete",
                "session_id": session_id,
                "phase": "chanakya",
                "round": round_before,
                "summary": c_summary,
                "verdict": str(state.get("verdict", "PENDING")),
                "timestamp": _utc_now(),
            },
        )

        if _is_waiting_for_user(state):
            waiting_payload = _build_waiting_payload(state, round_before)
            state["pending_user_action"] = waiting_payload
            shared = _ensure_shared_context(state)
            shared["user_arbitration_pending"] = True
            shared["pending_user_action"] = waiting_payload
            store.append_message(
                A2AEnvelope(
                    session_id=session_id,
                    round_num=round_before,
                    sender="chanakya",
                    receiver="user",
                    message_type=MessageType.CLARIFICATION_REQUEST,
                    content=str(waiting_payload.get("question", "")),
                    evidence={"waiting": waiting_payload},
                    confidence_score=float(waiting_payload.get("confidence", 0) or 0) / 100.0,
                    source="cli_runner",
                    task_type="arbitration",
                )
            )
            summary = _waiting_summary(state, waiting_payload)
            store.update_session(
                session_id,
                status="waiting_user",
                current_round=int(state.get("current_round", round_before)),
                verdict=str(state.get("verdict", "BLOCKED")),
                summary=summary,
                state_json=_safe_state(state),
            )
            _emit_progress(
                progress_callback,
                {
                    "type": "status",
                    "session_id": session_id,
                    "status": "waiting_user",
                    "round": int(state.get("current_round", round_before)),
                    "verdict": str(state.get("verdict", "BLOCKED")),
                    "summary": summary,
                    "timestamp": _utc_now(),
                },
            )
            return RunResult(
                session_id=session_id,
                status="waiting_user",
                verdict=str(state.get("verdict", "BLOCKED")),
                current_round=int(state.get("current_round", round_before)),
                max_rounds=int(state.get("max_rounds", 5) or 5),
                summary=summary,
            )

        if state.get("verdict") == "LGTM":
            break

        _emit_progress(
            progress_callback,
            {
                "type": "phase",
                "session_id": session_id,
                "phase": "aryabhata",
                "round": round_before,
                "status": "running",
                "timestamp": _utc_now(),
            },
        )
        state = await aryabhata_fix_node_async(state)
        validation = state.get("aryabhata_validation") if isinstance(state.get("aryabhata_validation"), dict) else {}
        blockers = validation.get("blockers") if isinstance(validation.get("blockers"), list) else []
        confidence = int(validation.get("confidence", 0) or 0)
        if blockers and confidence >= 85:
            state["verdict"] = "BLOCKED"
            state["hard_block_reason"] = {
                "reason": "strong_evidence_block",
                "confidence": confidence,
                "blocker_count": len(blockers),
            }
            shared = _ensure_shared_context(state)
            shared["user_arbitration_pending"] = True
        a_summary = _aryabhata_summary(state)
        store.append_round(
            session_id=session_id,
            round_num=round_before,
            phase="aryabhata",
            summary=a_summary,
            state_json=_round_state_snapshot(state),
        )
        store.update_session(
            session_id,
            current_round=int(state.get("current_round", round_before)),
            verdict=str(state.get("verdict", "PENDING")),
            summary={"phase": "aryabhata", **a_summary},
            state_json=_safe_state(state),
        )
        _emit_progress(
            progress_callback,
            {
                "type": "phase_complete",
                "session_id": session_id,
                "phase": "aryabhata",
                "round": round_before,
                "summary": a_summary,
                "verdict": str(state.get("verdict", "PENDING")),
                "timestamp": _utc_now(),
            },
        )

        if _is_waiting_for_user(state):
            waiting_payload = _build_waiting_payload(state, round_before)
            state["pending_user_action"] = waiting_payload
            shared = _ensure_shared_context(state)
            shared["user_arbitration_pending"] = True
            shared["pending_user_action"] = waiting_payload
            store.append_message(
                A2AEnvelope(
                    session_id=session_id,
                    round_num=round_before,
                    sender="aryabhata",
                    receiver="user",
                    message_type=MessageType.CLARIFICATION_REQUEST,
                    content=str(waiting_payload.get("question", "")),
                    evidence={"waiting": waiting_payload},
                    confidence_score=float(waiting_payload.get("confidence", 0) or 0) / 100.0,
                    source="cli_runner",
                    task_type="arbitration",
                )
            )
            summary = _waiting_summary(state, waiting_payload)
            store.update_session(
                session_id,
                status="waiting_user",
                current_round=int(state.get("current_round", round_before)),
                verdict=str(state.get("verdict", "BLOCKED")),
                summary=summary,
                state_json=_safe_state(state),
            )
            _emit_progress(
                progress_callback,
                {
                    "type": "status",
                    "session_id": session_id,
                    "status": "waiting_user",
                    "round": int(state.get("current_round", round_before)),
                    "verdict": str(state.get("verdict", "BLOCKED")),
                    "summary": summary,
                    "timestamp": _utc_now(),
                },
            )
            return RunResult(
                session_id=session_id,
                status="waiting_user",
                verdict=str(state.get("verdict", "BLOCKED")),
                current_round=int(state.get("current_round", round_before)),
                max_rounds=int(state.get("max_rounds", 5) or 5),
                summary=summary,
            )

        if state.get("verdict") == "LGTM":
            break
        if state.get("verdict") == "BLOCKED":
            break
        if round_before >= max_rounds:
            break
        next_round = int(state.get("current_round", round_before) or round_before)
        if next_round <= round_before:
            break

    if state.get("verdict") == "PENDING":
        state["verdict"] = "NEEDS_WORK"

    learning = store.learn_from_session(session_id, _safe_state(state), subsystem=subsystem)
    summary = _final_summary(state, kb_patterns, learning)
    store.update_session(
        session_id,
        status="completed",
        current_round=int(state.get("current_round", 1) or 1),
        verdict=str(state.get("verdict", "NEEDS_WORK")),
        summary=summary,
        state_json=_safe_state(state),
    )
    _emit_progress(
        progress_callback,
        {
            "type": "status",
            "session_id": session_id,
            "status": "completed",
            "round": int(state.get("current_round", 1) or 1),
            "verdict": str(state.get("verdict", "NEEDS_WORK")),
            "summary": summary,
            "timestamp": _utc_now(),
        },
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
    return _run_coro_sync(run_new_session(store, **kwargs))


def resume_session_sync(store: CLISessionStore, session_id: str) -> RunResult:
    session = store.get_session(session_id)
    if not session:
        raise ValueError(f"Session not found: {session_id}")
    if session.status == "waiting_user":
        return RunResult(
            session_id=session_id,
            status=session.status,
            verdict=session.verdict,
            current_round=session.current_round,
            max_rounds=session.max_rounds,
            summary=session.summary,
        )
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
    return _run_coro_sync(run_existing_state(store, session_id=session_id, state=state))


async def continue_with_user_input(
    store: CLISessionStore,
    *,
    session_id: str,
    response: str,
    mode: str = "clarify",
    override_decision: str = "resume",
) -> RunResult:
    session = store.get_session(session_id)
    if not session:
        raise ValueError(f"Session not found: {session_id}")

    state = dict(session.state_json or {})
    if not state:
        raise ValueError(f"Session {session_id} has no resumable state")

    state["session_id"] = session_id
    shared = _ensure_shared_context(state)
    shared["user_arbitration_pending"] = False
    shared["pending_user_action"] = None
    shared["last_user_input"] = {
        "mode": mode,
        "response": str(response or ""),
        "decision": str(override_decision or "resume"),
        "timestamp": _utc_now(),
    }
    state["pending_user_action"] = None
    state["interrupt_hint"] = f"user_{mode}: {str(response or '').strip()}"[:800]

    clean_mode = str(mode or "clarify").lower()
    clean_decision = str(override_decision or "resume").lower()

    if clean_mode == "override" and clean_decision in {"approve", "needs_work"}:
        final_verdict = "LGTM" if clean_decision == "approve" else "NEEDS_WORK"
        state["verdict"] = final_verdict
        summary = {
            "phase": "user_override",
            "decision": clean_decision,
            "note": str(response or "").strip(),
            "timestamp": _utc_now(),
        }
        store.append_message(
            A2AEnvelope(
                session_id=session_id,
                round_num=int(state.get("current_round", 1) or 1),
                sender="user",
                receiver="system",
                message_type=MessageType.APPROVE if final_verdict == "LGTM" else MessageType.ESCALATE,
                content=f"User override decision: {clean_decision}. {str(response or '').strip()}",
                evidence={"mode": clean_mode, "decision": clean_decision},
                confidence_score=1.0,
                source="cli",
                task_type="user_override",
            )
        )
        store.update_session(
            session_id,
            status="completed",
            current_round=int(state.get("current_round", 1) or 1),
            verdict=final_verdict,
            summary=summary,
            state_json=_safe_state(state),
        )
        return RunResult(
            session_id=session_id,
            status="completed",
            verdict=final_verdict,
            current_round=int(state.get("current_round", 1) or 1),
            max_rounds=int(state.get("max_rounds", session.max_rounds) or session.max_rounds),
            summary=summary,
        )

    state["verdict"] = "PENDING"
    if int(state.get("current_round", 1) or 1) <= 0:
        state["current_round"] = 1

    store.append_message(
        A2AEnvelope(
            session_id=session_id,
            round_num=int(state.get("current_round", 1) or 1),
            sender="user",
            receiver="chanakya",
            message_type=_user_response_message_type(clean_mode),
            content=str(response or "").strip(),
            evidence={"mode": clean_mode, "decision": clean_decision},
            confidence_score=1.0,
            source="cli",
            task_type="clarification",
        )
    )
    store.update_session(
        session_id,
        status="running",
        current_round=int(state.get("current_round", 1) or 1),
        verdict="PENDING",
        summary={
            "phase": "user_response",
            "mode": clean_mode,
            "decision": clean_decision,
        },
        state_json=_safe_state(state),
    )
    return await run_existing_state(store, session_id=session_id, state=state)


def continue_with_user_input_sync(
    store: CLISessionStore,
    *,
    session_id: str,
    response: str,
    mode: str = "clarify",
    override_decision: str = "resume",
) -> RunResult:
    return _run_coro_sync(
        continue_with_user_input(
            store,
            session_id=session_id,
            response=response,
            mode=mode,
            override_decision=override_decision,
        )
    )
