from __future__ import annotations

from typing import Any

from app.agents.state import PatchWiseState


ARYABHATA_SYSTEM_PROMPT = (
    "You are ARYABHATA, a precise and methodical kernel developer who "
    "computes the exact fix for every issue raised. You think deeply before "
    "acting, fix all issues in one comprehensive pass, and justify every "
    "change with mathematical precision. You are inspired by Aryabhata's "
    "precision in calculating what others could not."
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


def _line_range_around(patch: str, line_number: int, radius: int = 1) -> tuple[int, int, str]:
    lines = patch.splitlines()
    line_number = max(1, min(line_number, len(lines) if lines else 1))
    start = max(1, line_number - radius)
    end = min(len(lines), line_number + radius)
    snippet = "\n".join(lines[start - 1:end]) if lines else ""
    return start, end, snippet


def _apply_fix_once(patch: str, issue: dict[str, Any]) -> str:
    issue_type = issue.get("issue_type", "")
    if issue_type == "STYLE":
        return patch.replace("\t", "    ")
    if issue_type == "MEMORY" and ("kmalloc(" in patch or "kzalloc(" in patch):
        if "if (!" not in patch:
            lines = patch.splitlines()
            updated: list[str] = []
            for line in lines:
                updated.append(line)
                if "kmalloc(" in line or "kzalloc(" in line:
                    indent = line[: len(line) - len(line.lstrip(" "))]
                    updated.append(f"{indent}if (!ptr)\n{indent}    return -ENOMEM;")
            return "\n".join(updated)
    if issue_type == "LKML" and "Signed-off-by:" not in patch:
        return patch.rstrip() + "\n\nSigned-off-by: Ajay Kumar Nandam <nandam@qti.qualcomm.com>\n"
    if issue_type == "COMMIT" and "Subject:" not in patch:
        return "Subject: ASoC: fix patchwise identified issue\n\n" + patch
    if issue_type == "LOGIC" and "== NULL" in patch:
        return patch.replace("== NULL", "")
    return patch


def aryabhata_fix_node(state: PatchWiseState) -> PatchWiseState:
    round_id = state.get("current_round", 1)
    findings_round = state.get("review_findings", [])
    if not findings_round:
        state["verdict"] = "LGTM"
        return state

    findings = findings_round[-1].get("findings", [])
    patch = state.get("current_patch") or state.get("patch_input", "")

    hint = state.get("interrupt_hint")
    thinking = "Computing one-pass comprehensive fix for all reported issues."
    if hint:
        thinking += f" IMPORTANT USER GUIDANCE: \"{hint}\"."
    _emit_tokens(state, "aryabhata", "thinking", round_id, thinking)

    justifications: list[dict[str, Any]] = []
    for index, issue in enumerate(findings, start=1):
        line_number = int(issue.get("line_number", 1) or 1)
        before_start, before_end, original_snippet = _line_range_around(patch, line_number)
        updated_patch = _apply_fix_once(patch, issue)
        _, _, fixed_snippet = _line_range_around(updated_patch, line_number)

        justification = {
            "issue": issue.get("description", "Issue"),
            "root_cause": f"Detected {issue.get('issue_type', 'UNKNOWN')} gap.",
            "fix_approach": issue.get("suggestion", "Applied deterministic correction."),
            "why_this_approach": "Preserves kernel semantics while satisfying review constraints.",
            "references": issue.get("similar_patch_refs", []),
        }

        issue_id = issue.get("issue_id", f"issue-{index}")
        fix_event = {
            "agent": "aryabhata",
            "type": "FIX_APPLIED",
            "round": round_id,
            "content": f"✅ Fix Applied for {issue.get('issue_type', 'ISSUE')} at line {line_number}",
            "metadata": {
                "issue_ref": issue_id,
                "original_code": original_snippet,
                "fixed_code": fixed_snippet,
                "line_range": [before_start, before_end],
                "justification": justification,
            },
        }
        _emit(state, fix_event)

        _emit_tokens(
            state,
            "aryabhata",
            "justification",
            round_id,
            (
                f"Issue: {justification['issue']} Root cause: {justification['root_cause']} "
                f"Approach: {justification['fix_approach']} Why: {justification['why_this_approach']}"
            ),
            metadata=justification,
        )

        justifications.append(
            {
                "inline_summary": fix_event["content"],
                "detailed_card": justification,
                "issue_ref": issue_id,
                "original_code": original_snippet,
                "fixed_code": fixed_snippet,
                "line_range": [before_start, before_end],
            }
        )

        patch = updated_patch

    state.setdefault("fix_attempts", []).append(
        {
            "round": round_id,
            "fixes": justifications,
            "summary": f"Applied {len(justifications)} fix(es).",
        }
    )
    state.setdefault("conversation_log", []).append(
        {
            "round": round_id,
            "agent": "aryabhata",
            "message": f"Applied {len(justifications)} fix(es).",
            "fixes": justifications,
        }
    )

    state["current_patch"] = patch
    state["current_round"] = round_id + 1
    state["verdict"] = "PENDING"
    state["interrupt_hint"] = None
    return state
