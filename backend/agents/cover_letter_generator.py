from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional


class CoverLetterGenerator:
    """
    Generates complete cover letters for patch series.
    Uses patch content + subsystem context + version history.
    """

    def generate(
        self,
        patches: list[str],
        subsystem: str,
        version: int,
        prev_version_url: Optional[str],
        version_context: Optional[dict[str, Any]],
        author_name: str,
        author_email: str,
    ) -> str:
        patch_summaries = self._extract_patch_summaries(patches)
        series_description = self._generate_series_description(patches, subsystem)
        changes_section = self._generate_changes_section(version, version_context)

        patch_count = len(patches)
        subject = f"[PATCH v{version} 0/{patch_count}] {subsystem}: {series_description}"

        body_lines = [
            f"This series {self._describe_series_action(patches, subsystem)}.",
            "",
            "Patches in this series:",
        ]

        for i, summary in enumerate(patch_summaries, 1):
            body_lines.append(f"  {i}. {summary}")

        if changes_section:
            body_lines.extend(["", changes_section, ""])
        else:
            body_lines.append("")

        if prev_version_url:
            body_lines.append(f"Link: {prev_version_url}")
            body_lines.append("")

        body_lines.append(f"Signed-off-by: {author_name} <{author_email}>")

        cover_letter = f"""From 0000000000000000000000000000000000000000 Mon Sep 17 00:00:00 2001
From: {author_name} <{author_email}>
Date: {datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000')}
Subject: {subject}

{chr(10).join(body_lines)}

---
{self._generate_diffstat(patches)}
 {patch_count} file(s) changed
"""
        return cover_letter

    def _extract_patch_summaries(self, patches: list[str]) -> list[str]:
        summaries: list[str] = []
        for patch in patches:
            subj_match = re.search(r"Subject: \[PATCH[^\]]*\]\s*(.*)", patch)
            if subj_match:
                summaries.append(subj_match.group(1).strip())
            else:
                summaries.append("Fix issue in patch")
        return summaries

    def _generate_series_description(self, patches: list[str], subsystem: str) -> str:
        subjects: list[str] = []
        for patch in patches:
            match = re.search(r"Subject: \[PATCH[^\]]*\]\s*(.*)", patch)
            if match:
                subjects.append(match.group(1))

        if not subjects:
            return "fix issues in audio driver"

        base = subjects[0].lower()
        if "fix" in base:
            return f"fix issues in {subsystem.lower()} driver"
        if "add" in base or "support" in base:
            return f"add support for {subsystem.lower()} features"
        if "remove" in base or "clean" in base:
            return f"cleanup {subsystem.lower()} driver"
        return f"update {subsystem.lower()} driver"

    def _describe_series_action(self, patches: list[str], subsystem: str) -> str:
        _ = patches
        return f"fixes various issues in the {subsystem} driver"

    def _generate_changes_section(
        self,
        version: int,
        version_context: Optional[dict[str, Any]],
    ) -> str:
        if version <= 1:
            return ""

        lines = [f"Changes in v{version}:"]
        if version_context and version_context.get("unaddressed_comments"):
            for comment in version_context["unaddressed_comments"]:
                summary = comment.get("summary") or comment.get("comment_text") or "review feedback"
                lines.append(f"  - Addressed: {summary}")
        else:
            lines.append("  - Addressed review comments from previous version")

        return "\n".join(lines)

    def _generate_diffstat(self, patches: list[str]) -> str:
        files_changed: set[str] = set()
        for patch in patches:
            diff_files = re.findall(r"diff --git a/([^\s]+)", patch)
            files_changed.update(diff_files)

        if not files_changed:
            return ""

        lines = []
        for path in sorted(files_changed):
            lines.append(f" {path} | [changes]")
        return "\n".join(lines)


async def generate_cover_letter_if_missing(
    state: dict[str, Any],
    llm,
    cover_letter_issues: list[dict[str, Any]],
) -> str:
    _ = llm
    _ = cover_letter_issues

    generator = CoverLetterGenerator()

    patches = state.get("patches") or [state.get("original_patch") or state.get("current_patch") or ""]
    subsystem = state.get("subsystem", "ASoC")
    version = int(state.get("version", 1) or 1)
    prev_url = state.get("prev_version_url")
    version_ctx = state.get("version_context")

    author_match = re.search(r"From: ([^<]+) <([^>]+)>", patches[0] if patches else "")
    author_name = author_match.group(1).strip() if author_match else "Author"
    author_email = author_match.group(2).strip() if author_match else "author@example.com"

    return generator.generate(
        patches=patches,
        subsystem=subsystem,
        version=version,
        prev_version_url=prev_url,
        version_context=version_ctx,
        author_name=author_name,
        author_email=author_email,
    )
