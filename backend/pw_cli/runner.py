from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

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


def _safe_state(state: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in state.items():
        if key.startswith("_"):
            continue
        if callable(value):
            continue
        sanitized[key] = value
    return json.loads(json.dumps(sanitized, ensure_ascii=False, default=str))


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
    return await run_existing_state(store, session_id=session_id, state=state)


async def run_existing_state(store: CLISessionStore, *, session_id: str, state: dict[str, Any]) -> RunResult:
    def _stream_callback(payload: dict[str, Any]) -> None:
        envelope = A2AEnvelope.from_agent_payload(session_id, payload)
        store.append_message(envelope)

    state["_stream_callback"] = _stream_callback
    max_rounds = int(state.get("max_rounds", 5) or 5)
    subsystem = str(state.get("subsystem", "audio") or "audio")
    kb_patterns = store.get_active_kb_patterns(subsystem=subsystem, limit=12)
    state["kb_active_patterns"] = kb_patterns
    shared = state.get("shared_a2a_context") if isinstance(state.get("shared_a2a_context"), dict) else {}
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
    summary = {
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
