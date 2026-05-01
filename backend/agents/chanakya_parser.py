from __future__ import annotations

import json
import re
from typing import List

from models.patch_models import ReviewIssue


class ChanakyaIssueParser:
    """Parse CHANAKYA structured JSON issue output into ReviewIssue objects."""

    def parse_review_output(
        self,
        raw_output: str,
        previous_issues: List[ReviewIssue],
    ) -> List[ReviewIssue]:
        issues: list[ReviewIssue] = []

        json_pattern = r"\{[^{}]*\"issue_id\"[^{}]*\}"
        matches = re.findall(json_pattern, raw_output, re.DOTALL)

        for match in matches:
            try:
                data = json.loads(match)
                issues.append(
                    ReviewIssue(
                        issue_id=data.get("issue_id", ""),
                        category=data.get("category", "STYLE"),
                        severity=data.get("severity", "WARNING"),
                        line_number=int(data.get("line_number", 0) or 0),
                        file_path=data.get("file_path", ""),
                        hunk_context=data.get("hunk_context", ""),
                        error_message=data.get("error_message", ""),
                        problematic_code=data.get("problematic_code", ""),
                        suggested_fix=data.get("suggested_fix", ""),
                        explanation=data.get("explanation", ""),
                        reference=data.get("reference"),
                        is_recurring=bool(data.get("is_recurring", False)),
                        previous_round=data.get("previous_round"),
                    )
                )
            except (json.JSONDecodeError, ValueError):
                continue

        previous_map = {issue.error_message[:50]: issue for issue in previous_issues}
        for issue in issues:
            key = issue.error_message[:50]
            if key in previous_map:
                issue.is_recurring = True
                issue.previous_round = previous_map[key].round_number

        return issues
