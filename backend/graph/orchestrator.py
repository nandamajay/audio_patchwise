from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any

from api.dependencies import session_manager
from api.ws_manager import websocket_manager
from app.agents.aryabhata import aryabhata_fix_node
from app.agents.chanakya import chanakya_review_node
from graph.interrupt_handler import interrupt_handler
from graph.patchwise_graph import on_state_change
from services.history_manager import history_manager
from session.session_manager import SessionStatus


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _detect_input_type(patch_input: dict[str, Any]) -> str:
    if patch_input.get("raw_text"):
        return "raw"
    if patch_input.get("file_path"):
        return "file"
    if patch_input.get("gerrit_url"):
        return "gerrit"
    if patch_input.get("lkml_url"):
        return "lore"
    return "raw"


def _dump_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _round_issues(round_payload: dict[str, Any]) -> list[dict[str, Any]]:
    return round_payload.get("findings", []) if isinstance(round_payload, dict) else []


def _extract_new_references(state: dict[str, Any], previous_count: int) -> list[dict[str, Any]]:
    refs = state.get("similar_patches", [])
    if not isinstance(refs, list):
        return []

    recent = refs[previous_count:]
    dedup: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ref in recent:
        if not isinstance(ref, dict):
            continue
        key = f"{ref.get('url','')}|{ref.get('title','')}"
        if key in seen:
            continue
        seen.add(key)
        dedup.append(ref)
    return dedup


def _aggregate_issue_counts(state: dict[str, Any]) -> tuple[int, int]:
    findings = state.get("review_findings", [])
    fixes = state.get("fix_attempts", [])

    total_found = 0
    for round_item in findings:
        total_found += len(_round_issues(round_item))

    total_fixed = 0
    for fix_round in fixes:
        total_fixed += len(fix_round.get("fixes", [])) if isinstance(fix_round, dict) else 0

    return total_found, total_fixed


async def chanakya_node(state: dict[str, Any], config: dict) -> dict[str, Any]:
    del config
    session_id = state["session_id"]

    reviewed = await chanakya_review_node(state)

    hint = await interrupt_handler.wait_for_resume(session_id)

    if interrupt_handler.is_aborted(session_id):
        session_manager.update_session(
            session_id,
            status=SessionStatus.INTERRUPTED,
            verdict="USER_ABORTED",
        )
        reviewed["verdict"] = "ABORT"
        return reviewed

    if hint:
        reviewed.setdefault("user_hints", []).append(
            {
                "round": reviewed.get("current_round", 0),
                "hint": hint,
                "timestamp": _utc_now(),
            }
        )

        await websocket_manager.broadcast(
            session_id,
            {
                "type": "interrupt_acknowledged",
                "agent": "system",
                "message": (
                    f"💡 User hint received: '{hint}'. "
                    f"Agents will incorporate this in Round {reviewed.get('current_round', 0) + 1}."
                ),
                "round": reviewed.get("current_round", 0),
            },
        )

        session_manager.update_session(
            session_id,
            status=SessionStatus.RUNNING,
            conversation=reviewed.get("conversation_log", []),
        )

    return reviewed


async def aryabhata_node(state: dict[str, Any], config: dict) -> dict[str, Any]:
    del config
    hints = state.get("user_hints", [])
    latest_hint = hints[-1]["hint"] if hints else None
    if latest_hint:
        state["interrupt_hint"] = latest_hint
    return aryabhata_fix_node(state)


async def run_session_loop(session_id: str) -> None:
    session = session_manager.get_session(session_id)
    if not session:
        return

    patch_input = session.patch_input or {}
    patch_text = (
        patch_input.get("raw_text")
        or patch_input.get("file_path", "")
        or patch_input.get("gerrit_url", "")
        or patch_input.get("lkml_url", "")
    )

    state: dict[str, Any] = {
        "session_id": session_id,
        "patch_input": patch_text,
        "kernel_version": session.context.get("kernel_version", "unknown"),
        "subsystem": session.context.get("subsystem", "alsa-asoc"),
        "source_path": session.context.get("source_path", ""),
        "llm_provider": session.config.get("llm_provider", "qgenie"),
        "llm_model": session.config.get("llm_model", "gpt-4o"),
        "max_rounds": session.max_rounds,
        "current_round": max(1, session.current_round or 1),
        "review_findings": session.review_report.get("review_findings", []) if session.review_report else [],
        "fix_attempts": session.review_report.get("fix_attempts", []) if session.review_report else [],
        "similar_patches": session.review_report.get("similar_patches", []) if session.review_report else [],
        "current_patch": session.final_patch or patch_text,
        "verdict": session.verdict or "PENDING",
        "interrupt_hint": None,
        "conversation_log": session.conversation or [],
        "quality_score": session.review_report.get("quality_score", 0.0) if session.review_report else 0.0,
        "latest_review": {},
        "fix_history": [],
        "previous_round_issues": session.review_report.get("previous_round_issues", []) if session.review_report else [],
        "version_issues": [],
        "messages": [],
        "user_hints": [],
    }
    state["_stream_callback"] = lambda payload: asyncio.create_task(
        websocket_manager.broadcast(session_id, payload)
    )

    if not history_manager.get_session(session_id):
        history_manager.create_session(
            patch=patch_text,
            input_type=_detect_input_type(patch_input),
            metadata={
                "subsystem": state["subsystem"],
                "kernel_version": state["kernel_version"],
                "source_path": state["source_path"],
                "llm_provider": state["llm_provider"],
                "llm_model": state["llm_model"],
                "max_rounds": state["max_rounds"],
            },
            session_id=session_id,
        )

    history_manager.save_message(
        session_id,
        "SYSTEM",
        "start",
        "PatchWise review loop started.",
        metadata={
            "max_rounds": state["max_rounds"],
            "subsystem": state["subsystem"],
        },
    )

    session_manager.update_session(session_id, status=SessionStatus.RUNNING)

    while state["current_round"] <= state["max_rounds"]:
        round_number = state["current_round"]
        await on_state_change(state, "round_started")
        before_patch = state.get("current_patch", "")
        before_refs = len(state.get("similar_patches", []))
        started_at = time.monotonic()

        state = await chanakya_node(state, {})
        await on_state_change(state, "chanakya_review_complete")
        latest_review = state.get("review_findings", [])[-1] if state.get("review_findings") else {}
        issues = _round_issues(latest_review)

        history_manager.save_message(
            session_id,
            "CHANAKYA",
            "review",
            _dump_json(latest_review),
            metadata={
                "round": round_number,
                "issues_found": len(issues),
            },
        )

        if state.get("verdict") in {"LGTM", "ABORT"}:
            if state.get("verdict") == "LGTM":
                await on_state_change(state, "lgtm")
            round_id = history_manager.save_round(
                session_id=session_id,
                round_number=round_number,
                chanakya_input=before_patch,
                chanakya_output={
                    "issues": issues,
                    "summary": latest_review.get("summary", ""),
                    "quality_score": latest_review.get("quality_score", state.get("quality_score", 0.0)),
                },
                aryabhata_input={},
                aryabhata_output={"fixed_count": 0, "fixes": []},
                previous_patch=before_patch,
                current_patch=before_patch,
                duration_secs=time.monotonic() - started_at,
                verdict="LGTM" if state.get("verdict") == "LGTM" else "ABORT",
            )
            for ref in _extract_new_references(state, before_refs):
                history_manager.save_reference(session_id, round_id, ref)
            break

        aryabhata_input = {"issues": issues, "round": round_number}
        state = await aryabhata_node(state, {})
        await on_state_change(state, "aryabhata_fix_complete")

        latest_fix = state.get("fix_attempts", [])[-1] if state.get("fix_attempts") else {}
        fixed_count = len(latest_fix.get("fixes", [])) if isinstance(latest_fix, dict) else 0

        history_manager.save_message(
            session_id,
            "ARYABHATA",
            "fix",
            _dump_json(latest_fix),
            metadata={
                "round": round_number,
                "issues_fixed": fixed_count,
            },
        )

        round_id = history_manager.save_round(
            session_id=session_id,
            round_number=round_number,
            chanakya_input=before_patch,
            chanakya_output={
                "issues": issues,
                "summary": latest_review.get("summary", ""),
                "quality_score": latest_review.get("quality_score", state.get("quality_score", 0.0)),
            },
            aryabhata_input=aryabhata_input,
            aryabhata_output={
                "fixed_count": fixed_count,
                "fixes": latest_fix.get("fixes", []) if isinstance(latest_fix, dict) else [],
            },
            previous_patch=before_patch,
            current_patch=state.get("current_patch", ""),
            duration_secs=time.monotonic() - started_at,
            verdict="CONTINUE",
        )
        for ref in _extract_new_references(state, before_refs):
            history_manager.save_reference(session_id, round_id, ref)

        total_found, total_fixed = _aggregate_issue_counts(state)
        history_manager.update_session(
            session_id,
            total_rounds=round_number,
            total_issues_found=total_found,
            total_issues_fixed=total_fixed,
            final_patch=state.get("current_patch", ""),
        )

        session_manager.update_session(
            session_id,
            current_round=state["current_round"],
            final_patch=state.get("current_patch", ""),
            conversation=state.get("conversation_log", []),
            review_report={
                "review_findings": state.get("review_findings", []),
                "fix_attempts": state.get("fix_attempts", []),
                "similar_patches": state.get("similar_patches", []),
                "quality_score": state.get("quality_score", 0.0),
                "previous_round_issues": state.get("previous_round_issues", []),
            },
        )

    final_verdict = state.get("verdict", "PENDING")
    if final_verdict == "LGTM":
        status = SessionStatus.COMPLETED
    elif final_verdict == "ABORT":
        status = SessionStatus.INTERRUPTED
        final_verdict = "USER_ABORTED"
    elif state.get("current_round", 0) > state.get("max_rounds", 0):
        final_verdict = "MAX_ROUNDS_REACHED"
        await on_state_change(state, "max_rounds_reached")
        status = SessionStatus.COMPLETED
    else:
        status = SessionStatus.FAILED

    session_manager.update_session(
        session_id,
        status=status,
        verdict=final_verdict,
        final_patch=state.get("current_patch", ""),
        conversation=state.get("conversation_log", []),
        review_report={
            "review_findings": state.get("review_findings", []),
            "fix_attempts": state.get("fix_attempts", []),
            "similar_patches": state.get("similar_patches", []),
            "quality_score": state.get("quality_score", 0.0),
            "previous_round_issues": state.get("previous_round_issues", []),
            "summary": f"Completed with verdict {final_verdict}",
            "justification": "See conversation log for per-fix details.",
            "rounds": state.get("current_round", 0),
        },
    )

    total_found, total_fixed = _aggregate_issue_counts(state)
    history_verdict = final_verdict
    if history_verdict == "MAX_ROUNDS_REACHED":
        history_verdict = "MAX_ROUNDS"
    if history_verdict == "USER_ABORTED":
        history_verdict = "INTERRUPTED"

    history_manager.update_session(
        session_id,
        verdict=history_verdict,
        final_patch=state.get("current_patch", ""),
        total_rounds=len(state.get("review_findings", [])),
        total_issues_found=total_found,
        total_issues_fixed=total_fixed,
        kb_contributed=1 if final_verdict == "LGTM" else 0,
    )

    history_manager.save_message(
        session_id,
        "SYSTEM",
        "summary",
        f"Session completed with verdict {final_verdict}.",
        metadata={
            "status": status.value,
            "verdict": final_verdict,
            "rounds": len(state.get("review_findings", [])),
        },
    )
