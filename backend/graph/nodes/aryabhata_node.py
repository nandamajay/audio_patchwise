from __future__ import annotations

from typing import Any

from agents.aryabhata_fix_engine import AryabhataFixEngine
from models.patch_models import LineEdit, ReviewIssue


def _default_line_fix(issue: ReviewIssue) -> LineEdit:
    problematic = issue.problematic_code.strip()
    suggested = issue.suggested_fix.strip()
    fixed_line = suggested or problematic
    if not fixed_line:
        fixed_line = issue.error_message
    return LineEdit(
        line_number=issue.line_number,
        original_line=problematic,
        fixed_line=fixed_line,
        issue_id=issue.issue_id,
        category=issue.category,
        justification="Applied targeted correction from structured review issue.",
    )


async def aryabhata_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Async node variant for direct use in graph experiments.
    """
    session_id = state["session_id"]
    current_patch = state.get("current_patch", "")
    review_data = state.get("latest_review", {})
    review_issues = [ReviewIssue.model_validate(item) for item in review_data.get("issues", [])]
    round_number = state.get("current_round", 1)

    callback = state.get("_stream_callback")
    if callable(callback):
        callback(
            {
                "agent": "ARYABHATA",
                "type": "thinking_start",
                "round": round_number,
                "content": f"Analyzing {len(review_issues)} issues from CHANAKYA Round {round_number}",
            }
        )

    fix_instructions = {issue.issue_id: _default_line_fix(issue) for issue in review_issues}

    engine = AryabhataFixEngine()
    fix_result = engine.apply_fixes_sync(
        current_patch=current_patch,
        review_issues=review_issues,
        llm_fixes=fix_instructions,
    )

    if callable(callback):
        callback(
            {
                "agent": "ARYABHATA",
                "type": "fix_complete",
                "round": round_number,
                "fix_summary": [
                    {
                        "issue_id": issue.issue_id,
                        "category": issue.category,
                        "line": issue.line_number,
                        "problem": issue.error_message,
                        "fix": fix_instructions[issue.issue_id].fixed_line,
                        "status": "FIXED",
                    }
                    for issue in review_issues
                ],
                "diff_from_previous": fix_result.diff_from_previous,
                "fixed_patch": fix_result.fixed_patch,
                "checkpatch_output": fix_result.validation_result.get("checkpatch_output", ""),
                "validation_passed": fix_result.validation_result.get("passed", False),
            }
        )

    state["current_patch"] = fix_result.fixed_patch
    state.setdefault("fix_history", []).append(
        {
            "round": round_number,
            "fixes_applied": len(fix_instructions),
            "diff": fix_result.diff_from_previous,
            "validation_passed": fix_result.validation_result.get("passed", False),
        }
    )
    return state
