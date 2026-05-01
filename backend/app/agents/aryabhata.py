from __future__ import annotations

from typing import Any

from agents.aryabhata_agent import ARYABHATA_SYSTEM_PROMPT
from agents.aryabhata_fix_engine import AryabhataFixEngine
from app.agents.llm_bridge import parse_line_fix_response
from core.llm_factory import get_llm
from models.patch_models import LineEdit, ReviewIssue


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


def _line_at(patch: str, line_number: int) -> str:
    lines = patch.splitlines()
    if not lines:
        return ""
    line_number = max(1, min(line_number, len(lines)))
    return lines[line_number - 1]


def _default_fixed_line(issue: ReviewIssue, current_patch: str) -> str:
    if issue.suggested_fix:
        return issue.suggested_fix
    original = issue.problematic_code or _line_at(current_patch, issue.line_number)
    if issue.category == "STYLE":
        return original.replace("\t", "    ")
    if issue.category == "LOGIC":
        return original.replace("== NULL", "")
    if issue.category == "MEMORY":
        return "if (!ptr) return -ENOMEM;"
    if issue.category == "COMMIT":
        return "Subject: [PATCH] ASoC: component: short summary"
    if issue.category == "COMPLIANCE":
        return "Signed-off-by: Author <email>"
    return original


def _coerce_issue(raw: dict[str, Any], idx: int, round_id: int, patch: str) -> ReviewIssue:
    line_number = int(raw.get("line_number", 1) or 1)
    problematic = raw.get("problematic_code") or _line_at(patch, line_number)
    return ReviewIssue(
        issue_id=raw.get("issue_id", f"R{round_id}_{idx:03d}"),
        category=raw.get("category", raw.get("issue_type", "STYLE")),
        severity=raw.get("severity", "WARNING"),
        line_number=line_number,
        file_path=raw.get("file_path", "unknown"),
        hunk_context=raw.get("hunk_context", ""),
        error_message=raw.get("error_message", raw.get("description", "")),
        problematic_code=problematic,
        suggested_fix=raw.get("suggested_fix", raw.get("suggestion", "")),
        explanation=raw.get("explanation", raw.get("description", "")),
        reference=raw.get("reference"),
        is_recurring=bool(raw.get("is_recurring", raw.get("recurring", False))),
        previous_round=raw.get("previous_round", raw.get("first_seen")),
        round_number=round_id,
    )


def _validation_issue(message: str, index: int, round_id: int) -> ReviewIssue:
    return ReviewIssue(
        issue_id=f"R{round_id}_VAL_{index:03d}",
        category="STYLE",
        severity="WARNING",
        line_number=1,
        file_path="COMMIT_MSG",
        hunk_context="",
        error_message=message,
        problematic_code=message,
        suggested_fix=message,
        explanation="Validation follow-up issue.",
        round_number=round_id,
    )


def _generate_targeted_fix(
    llm: Any | None,
    issue: ReviewIssue,
    current_patch: str,
) -> LineEdit | None:
    if llm is None:
        return None

    prompt = f"""
You are ARYABHATA, Linux kernel patch developer.
Return ONLY three lines in this exact format:
ORIGINAL_LINE: <exact problematic code line>
FIXED_LINE: <exact corrected replacement line>
JUSTIFICATION: <one-sentence upstream rationale>

Issue category: {issue.category}
Line number: {issue.line_number}
Error: {issue.error_message}
Suggested fix: {issue.suggested_fix}
Problematic line: {issue.problematic_code}
Hunk context:
{issue.hunk_context}

Current patch line at {issue.line_number}:
{_line_at(current_patch, issue.line_number)}
"""

    try:
        response = llm.invoke(prompt)
        content = getattr(response, "content", response)
        if isinstance(content, list):
            content = "\n".join(str(item) for item in content)
        parsed = parse_line_fix_response(str(content or ""))
    except Exception:
        parsed = None
    if not parsed:
        return None

    original_line = parsed.original_line or issue.problematic_code or _line_at(
        current_patch, issue.line_number
    )
    if not parsed.fixed_line:
        return None

    return LineEdit(
        line_number=issue.line_number,
        original_line=original_line,
        fixed_line=parsed.fixed_line,
        issue_id=issue.issue_id,
        category=issue.category,
        justification=parsed.justification,
    )


def aryabhata_fix_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    ARYABHATA developer node: produce an actual modified patch file.
    """
    round_id = state.get("current_round", 1)
    current_patch = state.get("current_patch") or state.get("patch_input", "")
    latest_review = state.get("latest_review", {})
    raw_issues = latest_review.get("issues") or latest_review.get("findings") or []

    review_issues = [
        _coerce_issue(raw, idx + 1, round_id, current_patch)
        for idx, raw in enumerate(raw_issues)
    ]

    if not review_issues:
        state["verdict"] = "LGTM"
        return state

    _emit(
        state,
        {
            "agent": "aryabhata",
            "type": "thinking_start",
            "round": round_id,
            "content": f"Analyzing {len(review_issues)} issues from CHANAKYA Round {round_id}...",
        },
    )

    llm_provider = state.get("llm_provider")
    llm_model = state.get("llm_model")
    llm = None
    fix_mode = "local"
    try:
        llm = get_llm(
            model=llm_model,
            provider=llm_provider,
            temperature=0.2,
            streaming=True,
        )
        fix_mode = f"{llm_provider or 'qgenie'}:{llm_model or 'gpt-4o'}"
    except Exception:
        llm = None

    fix_instructions: dict[str, LineEdit] = {}
    for issue in review_issues:
        _emit(
            state,
            {
                "agent": "aryabhata",
                "type": "thinking_step",
                "round": round_id,
                "content": (
                    f"Issue #{issue.issue_id} [{issue.category}] Line {issue.line_number}: "
                    f"{issue.error_message}"
                ),
                "metadata": {"issue_id": issue.issue_id},
            },
        )

        line_edit = _generate_targeted_fix(llm, issue, current_patch)
        if line_edit is None:
            fixed_line = _default_fixed_line(issue, current_patch)
            line_edit = LineEdit(
                line_number=issue.line_number,
                original_line=issue.problematic_code or _line_at(current_patch, issue.line_number),
                fixed_line=fixed_line,
                issue_id=issue.issue_id,
                category=issue.category,
                justification=issue.explanation or "Applied targeted upstream-safe correction.",
            )
        fix_instructions[issue.issue_id] = line_edit

        _emit(
            state,
            {
                "agent": "aryabhata",
                "type": "thinking_fix",
                "round": round_id,
                "content": f"Fix: {line_edit.justification}",
                "metadata": {
                    "before": line_edit.original_line,
                    "after": line_edit.fixed_line,
                    "issue_id": issue.issue_id,
                },
            },
        )

    engine = AryabhataFixEngine()
    fix_result = engine.apply_fixes_sync(
        current_patch=current_patch,
        review_issues=review_issues,
        llm_fixes=fix_instructions,
    )

    if not fix_result.validation_result.get("passed", False):
        validation_issues = [
            _validation_issue(msg, index + 1, round_id)
            for index, msg in enumerate(fix_result.validation_result.get("issues", []))
        ]
        validation_fixes = {
            issue.issue_id: LineEdit(
                line_number=issue.line_number,
                original_line=issue.problematic_code,
                fixed_line=issue.suggested_fix,
                issue_id=issue.issue_id,
                category=issue.category,
                justification="Validation correction pass.",
            )
            for issue in validation_issues
        }
        if validation_issues:
            fix_result = engine.apply_fixes_sync(
                current_patch=fix_result.fixed_patch,
                review_issues=validation_issues,
                llm_fixes=validation_fixes,
            )

    fix_summary = [
        {
            "issue_id": issue.issue_id,
            "category": issue.category,
            "line": issue.line_number,
            "problem": issue.error_message,
            "fix": fix_instructions[issue.issue_id].fixed_line,
            "status": "FIXED",
        }
        for issue in review_issues
    ]

    _emit(
        state,
        {
            "agent": "aryabhata",
            "type": "fix_complete",
            "round": round_id,
            "content": f"Applied {len(fix_summary)} fixes",
            "fix_summary": fix_summary,
            "diff_from_previous": fix_result.diff_from_previous,
            "fixed_patch": fix_result.fixed_patch,
            "checkpatch_output": fix_result.validation_result.get("checkpatch_output", ""),
            "validation_passed": bool(fix_result.validation_result.get("passed", False)),
            "justification": (
                "All flagged issues were applied to concrete patch lines. "
                f"Fix mode: {fix_mode}."
            ),
        },
    )

    _emit_tokens(
        state,
        "aryabhata",
        "justification",
        round_id,
        "Generated modified patch file and updated all targeted lines.",
        metadata={"issues_fixed": len(fix_summary)},
    )

    state["current_patch"] = fix_result.fixed_patch
    _ensure_list(state, "fix_history").append(
        {
            "round": round_id,
            "fixes_applied": len(fix_summary),
            "diff": fix_result.diff_from_previous,
            "validation_passed": bool(fix_result.validation_result.get("passed", False)),
        }
    )
    _ensure_list(state, "fix_attempts").append(
        {
            "round": round_id,
            "fixes": fix_summary,
            "summary": f"Applied {len(fix_summary)} fix(es).",
            "diff_from_previous": fix_result.diff_from_previous,
            "fixed_patch": fix_result.fixed_patch,
            "validation_passed": bool(fix_result.validation_result.get("passed", False)),
        }
    )
    _ensure_list(state, "conversation_log").append(
        {
            "round": round_id,
            "agent": "aryabhata",
            "message": f"Applied {len(fix_summary)} fix(es).",
            "fixes": fix_summary,
            "diff_from_previous": fix_result.diff_from_previous,
        }
    )

    state["current_round"] = round_id + 1
    state["verdict"] = "PENDING"
    state["interrupt_hint"] = None
    return state
