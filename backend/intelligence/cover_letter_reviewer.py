"""
Cover-letter reviewer for LKML patch series.
"""
from __future__ import annotations

import re
from typing import Optional


class CoverLetterReviewer:
    REQUIRED_CHECKS = [
        "subject_format",
        "changelog_section",
        "previous_version_link",
        "patch_count_match",
        "diffstat_present",
        "signed_off_by",
    ]

    def review(self, cover_letter: Optional[str], patch_series: list[str]) -> list[dict]:
        if not cover_letter:
            if len(patch_series) > 1:
                return [
                    {
                        "type": "COVER_MISSING",
                        "severity": "CRITICAL",
                        "description": "No cover letter found for patch series",
                        "suggested_fix": "ARYABHATA can generate a cover letter template",
                        "auto_fix": True,
                    }
                ]
            return []

        issues: list[dict] = []

        if not re.search(r"Subject:.*\[PATCH v?\d+ 0/\d+\]", cover_letter):
            issues.append(
                {
                    "type": "COVER_SUBJECT",
                    "severity": "CRITICAL",
                    "line_number": self._find_line(cover_letter, "Subject:"),
                    "description": "Subject must follow format: [PATCH vN 0/M] description",
                    "problematic_code": self._extract_subject(cover_letter),
                    "suggested_fix": "[PATCH v{N} 0/{M}] {subsystem}: brief description",
                    "explanation": "LKML series cover letters require version and patch count in subject.",
                }
            )

        if not re.search(r"changes in v\d+", cover_letter, re.IGNORECASE):
            issues.append(
                {
                    "type": "COVER_CHANGELOG",
                    "severity": "CRITICAL",
                    "description": "Missing changelog section for versioned series",
                    "suggested_fix": "Add 'Changes in vN:' section with deltas from prior version.",
                    "explanation": "Maintainers use this to focus review on incremental updates.",
                }
            )

        version = self._extract_version(cover_letter)
        if version and version > 1 and "Link:" not in cover_letter:
            issues.append(
                {
                    "type": "COVER_LINK",
                    "severity": "CRITICAL",
                    "description": f"Missing Link: to v{version - 1} thread",
                    "suggested_fix": "Link: https://lore.kernel.org/alsa-devel/<message-id>/",
                    "explanation": "Version links preserve review history and reviewer context.",
                }
            )

        declared = re.search(r"\[PATCH[^\]]*0/(\d+)\]", cover_letter)
        if declared:
            declared_count = int(declared.group(1))
            actual_count = len(patch_series)
            if declared_count != actual_count:
                issues.append(
                    {
                        "type": "COVER_PATCH_COUNT",
                        "severity": "CRITICAL",
                        "description": f"Cover declares {declared_count} patches but found {actual_count}",
                        "suggested_fix": f"Update subject to 0/{actual_count}.",
                        "explanation": "Patch count mismatch can break maintainer review flow.",
                    }
                )

        if "---" in cover_letter and not re.search(r"\s+\d+\s+files?\s+changed", cover_letter):
            issues.append(
                {
                    "type": "COVER_DIFFSTAT",
                    "severity": "WARNING",
                    "description": "Missing or incomplete diffstat in cover letter",
                    "suggested_fix": "Include short diffstat from git format-patch output.",
                    "explanation": "Diffstat helps reviewers judge scope quickly.",
                }
            )

        if "Signed-off-by:" not in cover_letter:
            issues.append(
                {
                    "type": "COVER_SIGNED_OFF",
                    "severity": "CRITICAL",
                    "description": "Missing Signed-off-by in cover letter",
                    "suggested_fix": "Signed-off-by: Your Name <your@email.com>",
                    "explanation": "DCO sign-off is required for kernel submissions.",
                }
            )

        return issues

    def _find_line(self, content: str, starts_with: str) -> int:
        for idx, line in enumerate(content.splitlines(), 1):
            if line.startswith(starts_with):
                return idx
        return 1

    def _extract_subject(self, content: str) -> str:
        match = re.search(r"Subject:(.*)", content)
        return match.group(1).strip() if match else ""

    def _extract_version(self, content: str) -> Optional[int]:
        match = re.search(r"\[PATCH v(\d+)", content, re.IGNORECASE)
        return int(match.group(1)) if match else None

    def generate_cover_letter_template(self, patches: list[str], subsystem: str = "ASoC") -> str:
        count = len(patches)
        return f"""From 0000000000000000000000000000000000000000 Mon Sep 17 00:00:00 2001
From: [Your Name] <[your@email.com]>
Date: [Date]
Subject: [PATCH v1 0/{count}] {subsystem}: [Brief description of series]

[Describe the purpose of this patch series here.
Explain what problem it solves and how.]

---
Changes in v1:
- Initial submission

[Include diffstat output here]

Signed-off-by: [Your Name] <[your@email.com]>
---
[Diffstat will appear here]
"""
