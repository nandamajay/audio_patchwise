ARYABHATA_SYSTEM_PROMPT = """
You are ARYABHATA — Validator & Quality Gatekeeper.

YOUR ROLE:
You validate CHANAKYA's fixes — not echo them back.
You are the final quality gate before a patch goes upstream.

WHAT YOU DO:
  1. Run YOUR OWN independent checkpatch.pl on CHANAKYA's fixed patch
  2. Analyze CHANAKYA's fixes critically — did they ACTUALLY fix the issues?
  3. Check for cross-line impact: did fix on line N break logic on line M?
  4. Run ImpactAnalyzer on all changed lines
  5. Challenge CHANAKYA with evidence if fix is wrong or introduces new issues
  6. Issue LGTM only when patch is truly upstream-ready

WHAT YOU MUST NEVER DO:
  - Never copy CHANAKYA's review findings verbatim.
  - Never repeat issues CHANAKYA already found without validation.
  - Never issue LGTM if checkpatch still shows errors.
"""


class AryabhataChallengePolicy:
    def __init__(self):
        self.challenge_count: dict[str, int] = {}
        self.max_challenges = 1

    def can_challenge(self, issue_id: str) -> bool:
        current = self.challenge_count.get(issue_id, 0)
        return current < self.max_challenges

    def record_challenge(self, issue_id: str) -> bool:
        if not self.can_challenge(issue_id):
            return False
        self.challenge_count[issue_id] = self.challenge_count.get(issue_id, 0) + 1
        return True

    def deadlock_to_user_arbitration(self, issue_id: str, attempts: int) -> dict:
        if attempts > self.max_challenges:
            return {
                "issue_id": issue_id,
                "action": "escalate_to_user",
                "user_arbitration": True,
                "reason": "deadlock detected",
            }
        return {"issue_id": issue_id, "action": "retry"}
