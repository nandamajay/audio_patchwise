from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from api.dependencies import session_manager
from api.ws_manager import websocket_manager
from app.agents.aryabhata import aryabhata_fix_node
from app.agents.chanakya import chanakya_review_node
from graph.interrupt_handler import interrupt_handler
from session.session_manager import SessionStatus


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def chanakya_node(state: dict[str, Any], config: dict) -> dict[str, Any]:
    del config
    session_id = state["session_id"]

    reviewed = chanakya_review_node(state)

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

    patch_text = (
        session.patch_input.get("raw_text")
        or session.patch_input.get("file_path", "")
        or session.patch_input.get("gerrit_url", "")
        or session.patch_input.get("lkml_url", "")
    )

    state: dict[str, Any] = {
        "session_id": session_id,
        "patch_input": patch_text,
        "kernel_version": session.context.get("kernel_version", "unknown"),
        "subsystem": session.context.get("subsystem", "alsa-asoc"),
        "source_path": session.context.get("source_path", ""),
        "llm_model": session.config.get("llm_provider", "gpt-4o"),
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
        "messages": [],
        "user_hints": [],
    }
    state["_stream_callback"] = lambda payload: asyncio.create_task(
        websocket_manager.broadcast(session_id, payload)
    )

    session_manager.update_session(session_id, status=SessionStatus.RUNNING)

    while state["current_round"] <= state["max_rounds"]:
        state = await chanakya_node(state, {})
        session_manager.update_session(
            session_id,
            current_round=state["current_round"],
            issues_found=state.get("review_findings", []),
            conversation=state.get("conversation_log", []),
            review_report={
                "review_findings": state.get("review_findings", []),
                "fix_attempts": state.get("fix_attempts", []),
                "similar_patches": state.get("similar_patches", []),
                "quality_score": state.get("quality_score", 0.0),
            },
        )

        if state.get("verdict") in {"LGTM", "ABORT"}:
            break

        state = await aryabhata_node(state, {})
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
            },
        )

    final_verdict = state.get("verdict", "PENDING")
    if final_verdict == "LGTM":
        status = SessionStatus.COMPLETED
    elif final_verdict == "ABORT":
        status = SessionStatus.INTERRUPTED
    elif state.get("current_round", 0) > state.get("max_rounds", 0):
        final_verdict = "MAX_ROUNDS_REACHED"
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
            "summary": f"Completed with verdict {final_verdict}",
            "justification": "See conversation log for per-fix details.",
            "rounds": state.get("current_round", 0),
        },
    )
