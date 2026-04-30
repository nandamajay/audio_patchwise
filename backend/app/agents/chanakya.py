from __future__ import annotations

from typing import Any

from app.agents.state import PatchWiseState
from app.skills.patchwise_skill import full_patch_analysis
from app.skills.search_skill import SearchSkill


CHANAKYA_SYSTEM_PROMPT = (
    "You are CHANAKYA, a sharp analytical kernel patch reviewer with the "
    "precision of a senior LKML maintainer. You question everything, miss "
    "nothing, and reference historical patches to strengthen your review. "
    "You review: coding style, logic correctness, memory/resource safety, "
    "LKML compliance, and commit message quality."
)


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


def chanakya_review_node(state: PatchWiseState) -> PatchWiseState:
    round_id = state.get("current_round", 1)
    patch_text = state.get("current_patch") or state.get("patch_input", "")
    source_context = state.get("source_path", "")

    hint = state.get("interrupt_hint")
    thinking = "Analyzing style, logic, memory safety, LKML compliance, and commit quality."
    if hint:
        thinking += f" Interrupt hint received: {hint}."
    _emit_tokens(state, "chanakya", "thinking", round_id, thinking)

    analyses = full_patch_analysis(patch_text, source_context)
    issue_map = {
        "style": "STYLE",
        "logic": "LOGIC",
        "memory": "MEMORY",
        "lkml": "LKML",
        "commit": "COMMIT",
    }

    findings: list[dict[str, Any]] = []
    for bucket, items in analyses.items():
        for issue in items:
            issue["issue_type"] = issue_map[bucket]
            findings.append(issue)

    search_skill = SearchSkill()
    similar_refs = search_skill.search(
        patch_text,
        subsystem=state.get("subsystem", "alsa-asoc"),
        sources=["lkml", "gerrit", "local"],
    )

    for finding in findings:
        finding["similar_patch_refs"] = similar_refs[:2]
        _emit(
            state,
            {
                "agent": "chanakya",
                "type": "finding",
                "round": round_id,
                "content": finding["description"],
                "metadata": {
                    "issue_type": finding["issue_type"],
                    "severity": finding["severity"],
                    "line_number": finding["line_number"],
                    "suggestion": finding["suggestion"],
                    "similar_patch_refs": finding["similar_patch_refs"],
                },
            },
        )

    for ref in similar_refs[:3]:
        _emit(
            state,
            {
                "agent": "chanakya",
                "type": "similar_patch",
                "round": round_id,
                "content": ref["title"],
                "metadata": ref,
            },
        )

    issue_count = len(findings)
    quality_score = max(0.0, 100.0 - float(issue_count * 16))
    verdict = "LGTM" if issue_count == 0 else "NEEDS_WORK"

    state.setdefault("review_findings", []).append(
        {
            "round": round_id,
            "findings": findings,
            "summary": f"Found {issue_count} issue(s).",
            "quality_score": quality_score,
        }
    )
    state.setdefault("similar_patches", []).extend(similar_refs)
    state.setdefault("conversation_log", []).append(
        {
            "round": round_id,
            "agent": "chanakya",
            "message": f"Review complete. {issue_count} issue(s).",
            "findings": findings,
        }
    )
    state["quality_score"] = quality_score
    state["verdict"] = verdict

    final_type = "lgtm" if verdict == "LGTM" else "verdict"
    _emit(
        state,
        {
            "agent": "chanakya",
            "type": final_type,
            "round": round_id,
            "content": "LGTM" if verdict == "LGTM" else "Needs work",
            "metadata": {"quality_score": quality_score, "issue_count": issue_count},
        },
    )

    state["interrupt_hint"] = None
    return state
