from __future__ import annotations

import json
from typing import Any

from app.agents.chanakya import CHANAKYA_SYSTEM_PROMPT, IssueTracker, chanakya_review_node
from core.llm_factory import get_llm
from core.patchwise_skill import PatchWiseSkill


class ChanakyaAgent:
    """
    CHANAKYA — The Reviewer Agent.
    Powered by QGenie LLM + Official PatchWise Skill.
    """

    def __init__(self, model: str | None = None, provider: str | None = None):
        self.provider = provider
        self.model = model
        self.llm = get_llm(
            model=model,
            provider=provider,
            temperature=0.1,
            streaming=True,
        )
        self.patchwise = PatchWiseSkill()

    async def review(self, state: dict[str, Any]) -> dict[str, Any]:
        patch_content = state.get("current_patch") or state.get("patch_input", "")

        pw_result = self.patchwise.review_patch_file(
            patch_content=patch_content,
            subsystem=state.get("subsystem", "sound/soc"),
            kernel_path=state.get("kernel_path") or state.get("source_path"),
        )

        llm_analysis_prompt = self._build_review_prompt(patch_content, pw_result, state)
        llm_response = await self.llm.ainvoke(llm_analysis_prompt)

        review_report = self._build_review_report(
            pw_result=pw_result,
            llm_response=llm_response,
            round_number=state.get("round_number", state.get("current_round", 1)),
        )

        state.setdefault("review_reports", []).append(review_report)
        state["current_issues"] = review_report.get("issues", [])
        return state

    def _build_review_prompt(self, patch: str, pw_result, state: dict[str, Any]) -> str:
        round_number = state.get("round_number", state.get("current_round", 1))
        return f"""You are CHANAKYA, a senior Linux kernel reviewer specializing
in ALSA/ASoC audio subsystem patches for Qualcomm.

You are reviewing Round {round_number} of this patch.

PATCHWISE ANALYSIS (from official PatchWise tool via QGenie):
{pw_result.raw_output[:3000]}

CHECKPATCH ISSUES FOUND: {len(pw_result.checkpatch_issues)}
AI REVIEW ISSUES FOUND: {len(pw_result.ai_review_issues)}

FULL PATCH CONTENT:
{patch}

PREVIOUS ROUNDS: {len(state.get('review_reports', []))}

YOUR TASK:
1. Build on top of PatchWise findings — add deeper logic/memory/compliance analysis
2. For EACH issue provide EXACTLY:
   - line_number: exact line in patch
   - problematic_code: the exact bad line(s)
   - suggested_fix: the exact corrected line(s)
   - explanation: why this violates kernel standards
   - reference: LKML/kernel doc link if available
3. Flag any issues that are RECURRING from previous rounds
4. Search your knowledge for similar ALSA/ASoC patches
5. End with LGTM verdict if all issues are resolved, or list remaining issues

OUTPUT FORMAT: Structured JSON matching ReviewReport schema.
DO NOT describe fixes in text — provide exact line replacements only.
"""

    def _build_review_report(self, pw_result, llm_response, round_number: int) -> dict[str, Any]:
        llm_text = getattr(llm_response, "content", llm_response)
        if isinstance(llm_text, list):
            llm_text = "\n".join(str(item) for item in llm_text)
        llm_text = str(llm_text or "")

        issues = list(pw_result.issues)
        parsed = None
        for candidate in (llm_text,):
            try:
                parsed = json.loads(candidate)
                break
            except Exception:
                continue

        if isinstance(parsed, dict) and isinstance(parsed.get("issues"), list):
            issues.extend(parsed["issues"])

        return {
            "round": round_number,
            "issues": issues,
            "findings": issues,
            "summary": f"Found {len(issues)} issue(s).",
            "patchwise_raw_output": pw_result.raw_output,
            "checkpatch_issue_count": len(pw_result.checkpatch_issues),
            "ai_issue_count": len(pw_result.ai_review_issues),
            "llm_raw": llm_text,
        }


__all__ = [
    "IssueTracker",
    "CHANAKYA_SYSTEM_PROMPT",
    "chanakya_review_node",
    "ChanakyaAgent",
]
