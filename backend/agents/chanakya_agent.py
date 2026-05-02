CHANAKYA_SYSTEM_PROMPT = """
You are CHANAKYA — Analyst & Patch Engineer for Linux kernel patch review.

YOUR ROLE:
You are BOTH the analyst AND the engineer who FIXES what you find.
You must review, fix, and regenerate a clean patch in the same step.

CORE REQUIREMENTS:
- Run patchwise tools when available (checkpatch, ai_code_review, LLMCommitAudit).
- Perform manual analysis beyond tool output.
- Fix every issue you find, not just list them.
- Output the fixed patch between <<<FIXED_PATCH_START>>> markers.
- Self-validate with checkpatch before handing off to ARYABHATA.
"""


def self_validate(patch_text: str) -> dict:
    """
    Self-validate CHANAKYA output before handing to ARYABHATA.
    Runs checkpatch when available and reports errors/warnings.
    """
    import os
    import subprocess
    import tempfile

    checkpatch = os.getenv("CHECKPATCH_PATH", "scripts/checkpatch.pl")
    if not os.path.exists(checkpatch):
        return {"status": "skipped", "errors": [], "warnings": [], "output": ""}

    with tempfile.NamedTemporaryFile(mode="w+", suffix=".patch", delete=True) as tmp:
        tmp.write(patch_text)
        tmp.flush()
        result = subprocess.run(
            [checkpatch, "--no-tree", "--strict", tmp.name],
            capture_output=True,
            text=True,
            check=False,
        )

    output = (result.stdout or "") + (result.stderr or "")
    errors = [line for line in output.splitlines() if line.startswith("ERROR:")]
    warnings = [line for line in output.splitlines() if line.startswith("WARNING:")]
    return {
        "status": "ok" if result.returncode == 0 else "issues",
        "errors": errors,
        "warnings": warnings,
        "output": output,
    }


CHANAKYA_ISSUE_FORMAT_PROMPT = """
MANDATORY ISSUE REPORTING FORMAT

For every issue, include all fields:
{
  "issue_id": "unique_id_per_round",
  "category": "STYLE|LOGIC|MEMORY|COMMIT|COMPLIANCE",
  "severity": "CRITICAL|WARNING|INFO",
  "line_number": <exact line number>,
  "file_path": "path/to/file.c",
  "hunk_context": "<5 lines before and after>",
  "error_message": "<exact finding>",
  "problematic_code": "<exact problematic line>",
  "suggested_fix": "<exact corrected line>",
  "explanation": "<why this is wrong and upstream standard>",
  "reference": "<kernel doc or LKML reference>",
  "is_recurring": <bool>,
  "previous_round": <int|null>
}

RECURRING ISSUE ESCALATION
- Mark is_recurring=true if unresolved from previous round.
- Escalate severity by one level.
- Include explicit instruction to modify the exact target line.
"""


class SurgicalScopeBuilder:
    def build_scope(self, touched_lines: list[int], impact_scope: dict | None = None) -> dict:
        impact_scope = impact_scope or {}
        neighbors = impact_scope.get("direct", [])
        touched_lines_impact = sorted(set(touched_lines or []) | set(neighbors or []))
        return {
            "surgical_scope": touched_lines_impact,
            "impact_scope": impact_scope,
            "touched_lines_impact": touched_lines_impact,
        }


class ChanakyaChallengeEngine:
    def evaluate_challenge(self, issue_id: str, evidence: dict) -> dict:
        strength = float(evidence.get("confidence", 0.0) or 0.0)
        accepts = strength >= 0.7 or bool(evidence.get("checkpatch_error"))
        if accepts:
            return self.withdraw_issue(issue_id, evidence)
        return {"issue_id": issue_id, "decision": "uphold", "reason": "insufficient evidence"}

    def withdraw_issue(self, issue_id: str, evidence: dict) -> dict:
        return {
            "issue_id": issue_id,
            "decision": "withdraw",
            "accepted_evidence": evidence,
        }

    def smart_hybrid_re_review(self, touched_lines: list[int], impact_scope: dict, new_issues: list[dict]) -> dict:
        # smart_hybrid strategy: surgical_first, escalate_full when touched scope keeps producing new blockers.
        builder = SurgicalScopeBuilder()
        scope = builder.build_scope(touched_lines, impact_scope)
        if any(i.get("severity") == "BLOCKING" for i in new_issues):
            return {
                "smart_hybrid": True,
                "surgical_first": True,
                "escalate_full_review": True,
                "scope": scope,
            }
        return {
            "smart_hybrid": True,
            "surgical_first": True,
            "escalate_full_review": False,
            "scope": scope,
        }
