from __future__ import annotations

import json
from typing import Any

from agents.aryabhata_fix_engine import AryabhataFixEngine
from core.llm_factory import get_llm
from models.patch_models import LineEdit, ReviewIssue


class AryabhataAgent:
    """
    ARYABHATA — The Developer Agent.
    Powered by QGenie LLM.
    """

    def __init__(self, model: str | None = None, provider: str | None = None):
        self.llm = get_llm(
            model=model,
            provider=provider,
            temperature=0.2,
            streaming=True,
        )
        self.fix_engine = AryabhataFixEngine()

    async def fix(self, state: dict[str, Any]) -> dict[str, Any]:
        issues = state.get("current_issues", [])
        patch_content = state.get("current_patch") or state.get("patch_input", "")

        fix_prompt = self._build_fix_prompt(issues, patch_content, state)
        llm_response = await self.llm.ainvoke(fix_prompt)

        round_number = state.get("round_number", state.get("current_round", 1))
        review_issues = [self._coerce_issue(item, idx + 1, round_number) for idx, item in enumerate(issues)]
        fix_instructions = self._parse_fix_instructions(llm_response, review_issues)

        fix_result = self.fix_engine.apply_fixes_sync(
            current_patch=patch_content,
            review_issues=review_issues,
            llm_fixes=fix_instructions,
        )

        state["current_patch"] = fix_result.fixed_patch
        state.setdefault("fix_history", []).append(
            {
                "round": round_number,
                "fixes_applied": len(fix_instructions),
                "validation": fix_result.validation_result,
            }
        )
        return state

    def _coerce_issue(self, raw: dict[str, Any], idx: int, round_number: int) -> ReviewIssue:
        return ReviewIssue(
            issue_id=raw.get("issue_id", f"R{round_number}_{idx:03d}"),
            category=raw.get("category", "STYLE"),
            severity=raw.get("severity", "WARNING"),
            line_number=int(raw.get("line_number", 1) or 1),
            file_path=raw.get("file_path", "unknown"),
            hunk_context=raw.get("hunk_context", ""),
            error_message=raw.get("error_message", raw.get("description", "")),
            problematic_code=raw.get("problematic_code", ""),
            suggested_fix=raw.get("suggested_fix", raw.get("suggestion", "")),
            explanation=raw.get("explanation", raw.get("description", "")),
            reference=raw.get("reference"),
            is_recurring=bool(raw.get("is_recurring", False)),
            previous_round=raw.get("previous_round"),
            round_number=round_number,
        )

    def _build_fix_prompt(self, issues: list[dict[str, Any]], patch: str, state: dict[str, Any]) -> str:
        round_number = state.get("round_number", state.get("current_round", 1))
        return f"""You are ARYABHATA, a senior Linux kernel developer specializing
in ALSA/ASoC audio subsystem patches for Qualcomm.

CHANAKYA has reviewed your patch and found {len(issues)} issues in Round {round_number}.

ISSUES TO FIX (from CHANAKYA via QGenie-powered PatchWise):
{json.dumps(issues, indent=2)}

CURRENT PATCH CONTENT:
{patch}

YOUR TASK — Fix ALL {len(issues)} issues in ONE response:
For EACH issue provide:
  - issue_id: the issue identifier
  - line_number: exact line to change
  - original_line: the exact current line
  - fixed_line: the exact replacement line
  - justification: WHY you made this change (kernel standards reference)

CRITICAL RULES:
- Output fixes as <<<FIXED_PATCH_START>>> ... <<<FIXED_PATCH_END>>>
- EVERY issue must be addressed — do NOT skip any
- Do NOT describe fixes in text — apply them directly in the patch
- Provide justification for EACH fix separately
- If you disagree with a fix, explain why and propose an alternative

OUTPUT: Fixed patch content + fix summary JSON
"""

    def _parse_fix_instructions(
        self,
        llm_response: Any,
        review_issues: list[ReviewIssue],
    ) -> dict[str, LineEdit]:
        content = getattr(llm_response, "content", llm_response)
        if isinstance(content, list):
            content = "\n".join(str(item) for item in content)
        text = str(content or "")

        parsed_items: list[dict[str, Any]] = []
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict) and isinstance(parsed.get("fixes"), list):
                parsed_items = parsed["fixes"]
            elif isinstance(parsed, list):
                parsed_items = parsed
        except Exception:
            parsed_items = []

        by_id: dict[str, LineEdit] = {}
        for issue in review_issues:
            fix = next((item for item in parsed_items if item.get("issue_id") == issue.issue_id), None)
            fixed_line = issue.suggested_fix or issue.problematic_code
            justification = issue.explanation or "Applied targeted fix."
            if isinstance(fix, dict):
                fixed_line = str(fix.get("fixed_line") or fixed_line)
                justification = str(fix.get("justification") or justification)

            by_id[issue.issue_id] = LineEdit(
                line_number=issue.line_number,
                original_line=issue.problematic_code,
                fixed_line=fixed_line,
                issue_id=issue.issue_id,
                category=issue.category,
                justification=justification,
            )

        return by_id


__all__ = ["AryabhataAgent"]
