from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Any, Dict, List

from app.skills.checkpatch_skill import run_checkpatch
from models.patch_models import FixResult, LineEdit, ReviewIssue


@dataclass
class ParsedPatch:
    from_line: str
    date_line: str
    subject_line: str
    commit_body: list[str]
    separator: str
    stats_section: list[str]
    diff_hunks: list[dict[str, Any]]


class AryabhataFixEngine:
    """
    Core fix engine: parse patch, apply targeted edits, and serialize patch.
    """

    def __init__(self) -> None:
        self.patch_parser = PatchParser()
        self.commit_fixer = CommitMessageFixer()
        self.code_fixer = CodeLineFixer()
        self.validator = PatchValidator(self.patch_parser)

    def apply_fixes_sync(
        self,
        current_patch: str,
        review_issues: List[ReviewIssue],
        llm_fixes: Dict[str, LineEdit],
    ) -> FixResult:
        parsed = self.patch_parser.parse(current_patch)

        commit_issues = [issue for issue in review_issues if issue.category == "COMMIT"]
        code_issues = [issue for issue in review_issues if issue.category != "COMMIT"]

        if commit_issues:
            parsed = self.commit_fixer.fix(parsed, commit_issues, llm_fixes)
        if code_issues:
            parsed = self.code_fixer.fix(parsed, code_issues, llm_fixes)

        fixed_patch_str = self.patch_parser.serialize(parsed)
        validation = self.validator.validate(fixed_patch_str, parsed)

        diff_lines = list(
            difflib.unified_diff(
                current_patch.splitlines(keepends=True),
                fixed_patch_str.splitlines(keepends=True),
                fromfile="before_fix",
                tofile="after_fix",
                lineterm="",
            )
        )

        return FixResult(
            fixed_patch=fixed_patch_str,
            applied_fixes=llm_fixes,
            validation_result=validation,
            diff_from_previous="".join(diff_lines),
            issues_addressed=[issue.issue_id for issue in review_issues],
            checkpatch_output=validation.get("checkpatch_output", ""),
        )


class PatchParser:
    """Parse .patch file into structured sections."""

    def parse(self, patch_content: str) -> ParsedPatch:
        lines = patch_content.split("\n")
        from_line = ""
        date_line = ""
        subject_line = ""

        separator_idx = None
        for idx, line in enumerate(lines):
            if line.startswith("From: ") and not from_line:
                from_line = line
            elif line.startswith("Date: ") and not date_line:
                date_line = line
            elif line.startswith("Subject: ") and not subject_line:
                subject_line = line
            elif line == "---":
                separator_idx = idx
                break

        if separator_idx is None:
            separator_idx = len(lines)

        # Header block includes empty lines and commit message area before "---".
        header_lines = lines[:separator_idx]
        if not subject_line:
            subject_line = "Subject: [PATCH] ASoC: patchwise auto-fix"

        # Build commit body from lines after subject header in header block.
        subject_pos = next(
            (i for i, line in enumerate(header_lines) if line.startswith("Subject: ")),
            -1,
        )
        if subject_pos >= 0:
            commit_body = header_lines[subject_pos + 1 :]
        else:
            commit_body = header_lines[3:] if len(header_lines) > 3 else []

        tail_lines = lines[separator_idx + 1 :] if separator_idx < len(lines) else []

        stats_section: list[str] = []
        diff_start = 0
        for idx, line in enumerate(tail_lines):
            if line.startswith("diff --git "):
                diff_start = idx
                break
            stats_section.append(line)
        else:
            diff_start = len(tail_lines)

        diff_lines = tail_lines[diff_start:]
        diff_hunks = self._parse_hunks(diff_lines)

        return ParsedPatch(
            from_line=from_line,
            date_line=date_line,
            subject_line=subject_line,
            commit_body=commit_body,
            separator="---",
            stats_section=stats_section,
            diff_hunks=diff_hunks,
        )

    def _parse_hunks(self, diff_lines: list[str]) -> list[dict[str, Any]]:
        hunks: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        for line in diff_lines:
            if line.startswith("diff --git "):
                if current:
                    hunks.append(current)
                file_path = ""
                parts = line.split()
                if len(parts) >= 4 and parts[2].startswith("a/"):
                    file_path = parts[2][2:]
                current = {"header": line, "file_path": file_path, "lines": [line]}
            elif current is not None:
                current["lines"].append(line)

        if current:
            hunks.append(current)
        return hunks

    def serialize(self, parsed: ParsedPatch) -> str:
        output: list[str] = []
        if parsed.from_line:
            output.append(parsed.from_line)
        if parsed.date_line:
            output.append(parsed.date_line)
        output.append(parsed.subject_line or "Subject: [PATCH] ASoC: patchwise auto-fix")

        if parsed.commit_body and parsed.commit_body[0] != "":
            output.append("")
        output.extend(parsed.commit_body)

        output.append(parsed.separator)
        output.extend(parsed.stats_section)

        if parsed.stats_section and parsed.stats_section[-1] != "":
            output.append("")

        for hunk in parsed.diff_hunks:
            output.extend(hunk["lines"])

        return "\n".join(output).strip("\n") + "\n"


class CommitMessageFixer:
    """Fix commit message issues (subject prefix/format/signed-off-by)."""

    SUBSYSTEM_PREFIXES = [
        "ASoC:",
        "ALSA:",
        "sound/soc:",
        "sound/core:",
        "sound/pci:",
        "sound/usb:",
        "sound/drivers:",
    ]

    def fix(
        self,
        parsed: ParsedPatch,
        issues: List[ReviewIssue],
        llm_fixes: dict[str, LineEdit],
    ) -> ParsedPatch:
        for issue in issues:
            error = issue.error_message.lower()
            if "subsystem prefix" in error:
                self._fix_subject_prefix(parsed)
            elif "subject" in error:
                self._fix_subject_format(parsed)
            elif "signed-off" in error:
                self._add_signed_off_by(parsed, issue)
            elif "description" in error and issue.issue_id in llm_fixes:
                parsed.commit_body = [llm_fixes[issue.issue_id].fixed_line]
        return parsed

    def _fix_subject_prefix(self, parsed: ParsedPatch) -> None:
        subject = parsed.subject_line
        match = re.match(r"(Subject: \[PATCH[^\]]*\]\s*)(.*)", subject)
        if not match:
            if not subject.startswith("Subject: "):
                parsed.subject_line = f"Subject: [PATCH] ASoC: {subject}".strip()
            return

        prefix, rest = match.groups()
        if not any(rest.startswith(item) for item in self.SUBSYSTEM_PREFIXES):
            parsed.subject_line = f"{prefix}ASoC: {rest}".strip()

    def _fix_subject_format(self, parsed: ParsedPatch) -> None:
        subject = parsed.subject_line.strip()
        subject = re.sub(r"\s+", " ", subject)
        if subject.endswith("."):
            subject = subject[:-1]
        if ":" not in subject.replace("Subject: [PATCH] ", "", 1):
            subject = f"Subject: [PATCH] ASoC: {subject.replace('Subject: ', '').strip()}"
        parsed.subject_line = subject

    def _add_signed_off_by(self, parsed: ParsedPatch, issue: ReviewIssue) -> None:
        author = issue.context.get("author") or "Author <email>"
        sob_line = f"Signed-off-by: {author}"
        body_text = "\n".join(parsed.commit_body)
        if "Signed-off-by:" not in body_text:
            if parsed.commit_body and parsed.commit_body[-1] != "":
                parsed.commit_body.append("")
            parsed.commit_body.append(sob_line)


class CodeLineFixer:
    """Fix code line issues in diff hunks."""

    def fix(
        self,
        parsed: ParsedPatch,
        issues: List[ReviewIssue],
        llm_fixes: dict[str, LineEdit],
    ) -> ParsedPatch:
        for issue in issues:
            fix = llm_fixes.get(issue.issue_id)
            if not fix:
                continue

            target_line = fix.original_line.strip()
            replacement = fix.fixed_line.rstrip("\n")

            for hunk in parsed.diff_hunks:
                if issue.file_path and hunk.get("file_path") and issue.file_path not in hunk["file_path"]:
                    continue

                new_lines: list[str] = []
                replaced = False
                for line in hunk["lines"]:
                    if replaced:
                        new_lines.append(line)
                        continue

                    if line and line[0] in {"+", " ", "-"}:
                        body = line[1:]
                        if target_line and target_line in body:
                            prefix = line[0]
                            new_lines.append(f"{prefix}{replacement}")
                            replaced = True
                            continue
                    new_lines.append(line)
                hunk["lines"] = new_lines
        return parsed


class PatchValidator:
    """Validate fixed patch before sending back to CHANAKYA."""

    def __init__(self, parser: PatchParser) -> None:
        self._parser = parser

    def validate(self, patch_text: str, parsed: ParsedPatch | None = None) -> dict:
        parsed = parsed or self._parser.parse(patch_text)
        issues_found: list[str] = []

        subject = parsed.subject_line or ""
        if not re.search(r"Subject:\s+\[PATCH[^\]]*\]\s+\w+:", subject):
            issues_found.append("Subject missing subsystem prefix")

        body_text = "\n".join(parsed.commit_body)
        if "Signed-off-by:" not in body_text:
            issues_found.append("Missing Signed-off-by")

        for line in patch_text.splitlines():
            if line.endswith(" ") or line.endswith("\t"):
                issues_found.append(f"Trailing whitespace: {line[:80]}")
            if len(line) > 100:
                issues_found.append(f"Line exceeds 100 characters: {line[:80]}")

        checkpatch = run_checkpatch(patch_text)
        checkpatch_output = checkpatch.get("output", "")
        if checkpatch.get("status") == "ok" and "ERROR:" in checkpatch_output:
            issues_found.append("checkpatch reported errors")

        return {
            "passed": len(issues_found) == 0,
            "issues": issues_found,
            "checkpatch_output": checkpatch_output or ("OK" if not issues_found else "\n".join(issues_found)),
        }
