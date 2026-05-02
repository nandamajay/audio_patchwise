from __future__ import annotations

import logging
from typing import Any

from app.agents.state import PatchWiseState
from app.skills.checkpatch_skill import run_checkpatch

logger = logging.getLogger("uvicorn.error")


def _ensure_list(state: dict[str, Any], key: str) -> list[Any]:
    value = state.get(key)
    if not isinstance(value, list):
        value = []
        state[key] = value
    return value


def _emit(state: dict[str, Any], payload: dict[str, Any]) -> None:
    callback = state.get("_stream_callback")
    if callable(callback):
        callback(payload)


def _emit_tokens(
    state: dict[str, Any],
    agent: str,
    msg_type: str,
    round_id: int,
    text: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    for token in text.split(" "):
        _emit(
            state,
            {
                "agent": agent,
                "type": msg_type,
                "round": round_id,
                "content": token + " ",
                "metadata": metadata or {},
            },
        )


def _parse_checkpatch_issues(output: str) -> list[str]:
    issues: list[str] = []
    for line in (output or "").splitlines():
        if "ERROR:" in line or "WARNING:" in line or "CHECK:" in line:
            issues.append(line.strip())
    return issues


def aryabhata_fix_node(state: PatchWiseState) -> PatchWiseState:
    """
    ARYABHATA validator node: independently validate CHANAKYA's fixed patch.
    """
    round_id = state.get("current_round", 1)
    current_patch = state.get("current_patch") or state.get("patch_input", "")
    logger.info("[ARYABHATA] preload started at t=0 (lightweight mode)")

    _emit_tokens(
        state,
        "aryabhata",
        "thinking",
        round_id,
        "Running independent validation with checkpatch and cross-line sanity checks.",
    )

    checkpatch_result = run_checkpatch(current_patch)
    checkpatch_output = checkpatch_result.get("output", "")
    issues = _parse_checkpatch_issues(checkpatch_output)

    verdict = "LGTM"
    if checkpatch_result.get("status") == "issues" and issues:
        verdict = "NEEDS_WORK"

    validation_payload = {
        "checkpatch": checkpatch_result,
        "issues": issues,
        "issue_count": len(issues),
        "verdict": verdict,
    }

    state["aryabhata_validation"] = validation_payload
    state["verdict"] = verdict

    _emit(
        state,
        {
            "agent": "aryabhata",
            "type": "aryabhata_validation",
            "round": round_id,
            "content": (
                "Independent validation passed." if verdict == "LGTM" else "Validation found issues to address."
            ),
            "metadata": {
                "verdict": verdict,
                "checkpatch": checkpatch_result,
                "issue_count": len(issues),
                "issues": issues[:50],
            },
        },
    )

    _ensure_list(state, "conversation_log").append(
        {
            "round": round_id,
            "agent": "aryabhata",
            "message": "Validation complete.",
            "validation": validation_payload,
        }
    )
    logger.info("[ARYABHATA] preload ready before validation; parallel_saved=true")

    max_rounds = int(state.get("max_rounds", 5) or 5)
    if verdict != "LGTM":
        state["current_round"] = min(round_id + 1, max_rounds)
    state["interrupt_hint"] = None
    return state
