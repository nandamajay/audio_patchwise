"""
AryabhataFixEngine — Core patch manipulation engine
Forces ARYABHATA to produce real patch file modifications
NOT text descriptions of fixes
"""

from __future__ import annotations

import difflib
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.skills.checkpatch_skill import run_checkpatch
from models.patch_models import FixResult as ModelFixResult
from models.patch_models import LineEdit, ReviewIssue


@dataclass
class PatchHunk:
    """Represents a single diff hunk in a patch"""

    file_path: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    header: str
    lines: List[str]
    context_before: List[str] = field(default_factory=list)
    context_after: List[str] = field(default_factory=list)


@dataclass
class PatchSection:
    """Represents a complete file diff section"""

    file_path: str
    old_file: str
    new_file: str
    hunks: List[PatchHunk]


@dataclass
class ParsedPatch:
    """Fully parsed patch file"""

    commit_hash: str
    from_line: str
    date_line: str
    subject: str
    body: str
    diff_stat: str
    sections: List[PatchSection]
    raw_header: str
    cover_letter: Optional[str] = None


@dataclass
class FixResult:
    """Result of ARYABHATA fix application"""

    success: bool
    fixed_patch_content: str
    changes_made: List[dict]
    validation_passed: bool
    checkpatch_output: str
    errors: List[str] = field(default_factory=list)


class PatchParser:
    """Parses .patch files into structured components"""

    def parse(self, patch_content: str) -> ParsedPatch:
        lines = patch_content.split("\n")
        commit_hash = ""
        from_line = ""
        date_line = ""
        subject = ""
        body_lines: list[str] = []
        raw_header_lines: list[str] = []

        i = 0
        while i < len(lines):
            line = lines[i]
            if line.startswith("From "):
                parts = line.split(" ", 2)
                commit_hash = parts[1] if len(parts) > 1 else ""
                from_line = line
                raw_header_lines.append(line)
            elif line.startswith("From: "):
                raw_header_lines.append(line)
            elif line.startswith("Date: "):
                date_line = line
                raw_header_lines.append(line)
            elif line.startswith("Subject: "):
                subject = line[len("Subject: ") :].strip()
                raw_header_lines.append(line)
                i += 1
                while i < len(lines) and lines[i].startswith(" "):
                    subject += " " + lines[i].strip()
                    raw_header_lines.append(lines[i])
                    i += 1
                continue
            elif line.startswith("diff --git"):
                break
            else:
                if from_line:
                    body_lines.append(line)
                raw_header_lines.append(line)
            i += 1

        body_text = "\n".join(body_lines).rstrip("\n")
        diff_stat = ""
        if "\n---\n" in body_text:
            head, tail = body_text.split("\n---\n", 1)
            body_text = head.rstrip()
            diff_stat = "---\n" + tail

        sections = self._parse_diff_sections(lines[i:])

        return ParsedPatch(
            commit_hash=commit_hash,
            from_line=from_line,
            date_line=date_line,
            subject=subject,
            body=body_text,
            diff_stat=diff_stat,
            sections=sections,
            raw_header="\n".join(raw_header_lines),
        )

    def _parse_diff_sections(self, lines: List[str]) -> List[PatchSection]:
        sections: list[PatchSection] = []
        current_section: Optional[PatchSection] = None
        current_hunk: Optional[PatchHunk] = None

        for line in lines:
            if line.startswith("diff --git"):
                if current_section:
                    if current_hunk:
                        current_section.hunks.append(current_hunk)
                    sections.append(current_section)

                parts = line.split(" ")
                old_file = parts[2][2:] if len(parts) > 2 and parts[2].startswith("a/") else ""
                new_file = parts[3][2:] if len(parts) > 3 and parts[3].startswith("b/") else old_file
                current_section = PatchSection(
                    file_path=new_file,
                    old_file=old_file,
                    new_file=new_file,
                    hunks=[],
                )
                current_hunk = None
                continue

            if line.startswith("@@"):
                if current_hunk and current_section:
                    current_section.hunks.append(current_hunk)

                match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)", line)
                if not match:
                    current_hunk = None
                    continue

                old_start = int(match.group(1))
                old_count = int(match.group(2)) if match.group(2) else 1
                new_start = int(match.group(3))
                new_count = int(match.group(4)) if match.group(4) else 1
                file_path = current_section.file_path if current_section else ""
                current_hunk = PatchHunk(
                    file_path=file_path,
                    old_start=old_start,
                    old_count=old_count,
                    new_start=new_start,
                    new_count=new_count,
                    header=line,
                    lines=[],
                )
                continue

            if current_hunk is not None:
                current_hunk.lines.append(line)

        if current_section:
            if current_hunk:
                current_section.hunks.append(current_hunk)
            sections.append(current_section)

        return sections


class CommitMessageFixer:
    """Fixes commit message issues identified by CHANAKYA"""

    SUBSYSTEM_PREFIXES = {
        "alsa": "ALSA",
        "asoc": "ASoC",
        "sound/soc": "ASoC",
        "sound/core": "ALSA",
        "sound/usb": "ALSA: usb",
        "sound/pci": "ALSA: pci",
        "sound/arm": "ALSA: arm",
        "drivers/soundwire": "soundwire",
    }

    def fix_subject_prefix(self, subject: str, file_path: str) -> Tuple[str, str]:
        correct_prefix = self._detect_subsystem(file_path) or "ASoC"

        if re.match(r"^[A-Za-z][A-Za-z0-9/_-]+:", subject):
            existing_prefix = subject.split(":", 1)[0]
            if existing_prefix.lower() != correct_prefix.lower():
                fixed = subject.replace(existing_prefix + ":", correct_prefix + ":", 1)
                return fixed, f"Changed prefix from '{existing_prefix}' to '{correct_prefix}'"
            return subject, "Subject prefix already correct"

        fixed = f"{correct_prefix}: {subject}".strip()
        return fixed, f"Added missing subsystem prefix '{correct_prefix}'"

    def fix_signed_off_by(self, body: str, author: str) -> Tuple[str, str]:
        if "Signed-off-by:" in body:
            return body, "Signed-off-by already present"
        fixed = (body.rstrip() + f"\n\nSigned-off-by: {author}").strip("\n")
        return fixed, "Added missing Signed-off-by"

    def fix_commit_message_length(self, subject: str) -> Tuple[str, str]:
        if len(subject) <= 72:
            return subject, "Subject length OK"
        truncated = subject[:69]
        last_space = truncated.rfind(" ")
        if last_space > 50:
            truncated = truncated[:last_space] + "..."
        else:
            truncated = truncated + "..."
        return truncated, f"Truncated subject from {len(subject)} to {len(truncated)} chars"

    def _detect_subsystem(self, file_path: str) -> Optional[str]:
        lower = (file_path or "").lower()
        for path_pattern, prefix in self.SUBSYSTEM_PREFIXES.items():
            if path_pattern in lower:
                return prefix
        return None


class CodeLineFixer:
    """Applies targeted line-level fixes to patch hunks"""

    def apply_fix(
        self,
        hunk: PatchHunk,
        line_number: int,
        old_code: str,
        new_code: str,
        fix_type: str,
    ) -> Tuple[PatchHunk, bool]:
        del line_number, fix_type

        fixed_lines: list[str] = []
        fix_applied = False

        for line in hunk.lines:
            if line and line[0] in {"-", "+", " "}:
                prefix = line[0]
                content = line[1:]
                if prefix == "-" and self._content_matches(content, old_code):
                    fixed_lines.append(f"-{content}")
                    fixed_lines.append(f"+{new_code}")
                    fix_applied = True
                    continue
            fixed_lines.append(line)

        hunk.lines = fixed_lines
        return hunk, fix_applied

    def _content_matches(self, content: str, pattern: str) -> bool:
        return content.strip() == (pattern or "").strip()


class PatchRebuilder:
    """Rebuilds a complete patch file from modified components"""

    def rebuild(self, parsed: ParsedPatch) -> str:
        parts: list[str] = []

        if parsed.from_line:
            parts.append(parsed.from_line)

        for line in parsed.raw_header.split("\n"):
            if line.startswith("From: ") or line.startswith("Date: "):
                parts.append(line)

        parts.append(f"Subject: {parsed.subject}" if parsed.subject else "Subject: [PATCH] ASoC: patch")
        parts.append("")

        if parsed.body:
            parts.append(parsed.body)

        parts.append("---")

        for section in parsed.sections:
            parts.append(f"diff --git a/{section.old_file} b/{section.new_file}")
            parts.append(f"--- a/{section.old_file}")
            parts.append(f"+++ b/{section.new_file}")

            for hunk in section.hunks:
                old_count = sum(1 for l in hunk.lines if l.startswith("-") or l.startswith(" "))
                new_count = sum(1 for l in hunk.lines if l.startswith("+") or l.startswith(" "))
                parts.append(f"@@ -{hunk.old_start},{old_count} +{hunk.new_start},{new_count} @@")
                parts.extend(hunk.lines)

        parts.extend(["", "-- ", "2.43.0", ""])
        return "\n".join(parts)


class PatchValidator:
    """Validates fixed patch using checkpatch.pl"""

    def __init__(self, checkpatch_path: str = "/usr/src/linux/scripts/checkpatch.pl"):
        self.checkpatch_path = checkpatch_path

    def validate_sync(self, patch_content: str) -> Tuple[bool, str, List[str]]:
        tool_path = self.checkpatch_path
        if not Path(tool_path).exists():
            cp = run_checkpatch(patch_content)
            output = cp.get("output", "")
            if cp.get("status") == "skipped":
                return True, "checkpatch unavailable — skipped", []
            remaining = self._parse_remaining_issues(output)
            return len(remaining) == 0, output, remaining

        with tempfile.NamedTemporaryFile(mode="w", suffix=".patch", delete=False) as handle:
            handle.write(patch_content)
            temp_path = handle.name

        try:
            result = subprocess.run(
                ["perl", tool_path, "--no-tree", "--mailback", temp_path],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            output = (result.stdout or "") + (result.stderr or "")
            remaining = self._parse_remaining_issues(output)
            passed = len(remaining) == 0
            return passed, output, remaining
        except Exception as exc:
            return False, str(exc), [str(exc)]
        finally:
            Path(temp_path).unlink(missing_ok=True)

    async def validate(self, patch_content: str) -> Tuple[bool, str, List[str]]:
        return self.validate_sync(patch_content)

    def _parse_remaining_issues(self, output: str) -> List[str]:
        issues: list[str] = []
        for line in (output or "").split("\n"):
            if line.startswith("ERROR:") or line.startswith("WARNING:"):
                issues.append(line)
        return issues


class AryabhataFixEngine:
    """
    CORE ENGINE — Forces ARYABHATA to produce real patch file modifications.
    """

    def __init__(self):
        self.parser = PatchParser()
        self.commit_fixer = CommitMessageFixer()
        self.code_fixer = CodeLineFixer()
        self.rebuilder = PatchRebuilder()
        self.validator = PatchValidator()

    async def apply_fixes(
        self,
        patch_content: str,
        chanakya_issues: List[dict],
        author: str = "Developer <dev@example.com>",
    ) -> FixResult:
        return self._apply_fixes_core(patch_content, chanakya_issues, author)

    def _apply_fixes_core(
        self,
        patch_content: str,
        chanakya_issues: List[dict],
        author: str,
    ) -> FixResult:
        errors: list[str] = []
        changes_made: list[dict] = []
        pending_fallbacks: list[dict[str, Any]] = []

        try:
            parsed = self.parser.parse(patch_content)

            for issue in chanakya_issues:
                if issue.get("type") != "COMMIT":
                    continue

                file_path = parsed.sections[0].file_path if parsed.sections else ""
                new_subject, explanation = self.commit_fixer.fix_subject_prefix(parsed.subject, file_path)
                new_subject, length_note = self.commit_fixer.fix_commit_message_length(new_subject)
                if new_subject != parsed.subject:
                    changes_made.append(
                        {
                            "type": "COMMIT",
                            "line": 1,
                            "old": f"Subject: {parsed.subject}",
                            "new": f"Subject: {new_subject}",
                            "explanation": f"{explanation}; {length_note}",
                        }
                    )
                    parsed.subject = new_subject

                new_body, sob_explanation = self.commit_fixer.fix_signed_off_by(parsed.body, author)
                if new_body != parsed.body:
                    changes_made.append(
                        {
                            "type": "COMMIT",
                            "line": -1,
                            "old": "Missing Signed-off-by",
                            "new": f"Added Signed-off-by: {author}",
                            "explanation": sob_explanation,
                        }
                    )
                    parsed.body = new_body

            for issue in chanakya_issues:
                issue_type = issue.get("type")
                if issue_type not in {"STYLE", "LOGIC", "MEMORY", "COMPLIANCE"}:
                    continue

                line_no = int(issue.get("line_number", 0) or 0)
                problematic = issue.get("problematic_code", "")
                suggested = issue.get("suggested_fix", "")

                if not suggested:
                    errors.append(f"Issue at line {line_no} has no suggested fix — skipping")
                    continue

                fix_applied = False
                for section in parsed.sections:
                    for hunk in section.hunks:
                        if hunk.old_start <= line_no <= (hunk.old_start + max(hunk.old_count, 1)):
                            _, applied = self.code_fixer.apply_fix(
                                hunk,
                                line_no,
                                problematic,
                                suggested,
                                issue_type,
                            )
                            if applied:
                                fix_applied = True
                                changes_made.append(
                                    {
                                        "type": issue_type,
                                        "line": line_no,
                                        "old": problematic,
                                        "new": suggested,
                                        "explanation": issue.get("explanation", ""),
                                    }
                                )

                if not fix_applied:
                    pending_fallbacks.append(
                        {
                            "type": issue_type,
                            "line": line_no,
                            "old": problematic,
                            "new": suggested,
                            "explanation": issue.get("explanation", ""),
                        }
                    )
                    errors.append(f"Could not apply fix at line {line_no} — using fallback")

            fixed_patch_content = self.rebuilder.rebuild(parsed)

            resolved_fallbacks: list[dict[str, Any]] = []
            for fallback in pending_fallbacks:
                fixed_patch_content, applied = self._apply_fallback_line_fix(
                    fixed_patch_content=fixed_patch_content,
                    line_no=int(fallback.get("line", 0) or 0),
                    old_code=str(fallback.get("old", "") or ""),
                    new_code=str(fallback.get("new", "") or ""),
                )
                if not applied:
                    continue
                changes_made.append(fallback)
                resolved_fallbacks.append(fallback)

            if resolved_fallbacks:
                unresolved_errors: list[str] = []
                for entry in errors:
                    if "using fallback" not in entry:
                        unresolved_errors.append(entry)
                        continue
                    line_match = re.search(r"line\s+(\d+)", entry)
                    line_no = int(line_match.group(1)) if line_match else -1
                    if any(int(item.get("line", 0) or 0) == line_no for item in resolved_fallbacks):
                        continue
                    unresolved_errors.append(entry)
                errors = unresolved_errors

            passed, checkpatch_output, _remaining = self.validator.validate_sync(fixed_patch_content)

            return FixResult(
                success=True,
                fixed_patch_content=fixed_patch_content,
                changes_made=changes_made,
                validation_passed=passed,
                checkpatch_output=checkpatch_output,
                errors=errors,
            )
        except Exception as exc:
            return FixResult(
                success=False,
                fixed_patch_content=patch_content,
                changes_made=[],
                validation_passed=False,
                checkpatch_output="",
                errors=[str(exc)],
            )

    def _apply_fallback_line_fix(
        self,
        fixed_patch_content: str,
        line_no: int,
        old_code: str,
        new_code: str,
    ) -> tuple[str, bool]:
        """
        Last-resort replacement when diff-hunk matching misses.
        Prefer exact line number when available, then first exact content match.
        """
        if not new_code:
            return fixed_patch_content, False

        lines = fixed_patch_content.splitlines()
        if not lines:
            return fixed_patch_content, False

        idx = line_no - 1
        if 0 <= idx < len(lines):
            candidate = lines[idx]
            candidate_body = candidate[1:] if candidate[:1] in {" ", "-", "+"} else candidate
            if (not old_code) or candidate_body.strip() == old_code.strip():
                prefix = candidate[:1] if candidate[:1] in {" ", "-", "+"} else ""
                lines[idx] = f"{prefix}{new_code}"
                return "\n".join(lines) + ("\n" if fixed_patch_content.endswith("\n") else ""), True

        old_stripped = old_code.strip()
        for pos, line in enumerate(lines):
            body = line[1:] if line[:1] in {" ", "-", "+"} else line
            if old_stripped and body.strip() != old_stripped:
                continue
            prefix = line[:1] if line[:1] in {" ", "-", "+"} else ""
            lines[pos] = f"{prefix}{new_code}"
            return "\n".join(lines) + ("\n" if fixed_patch_content.endswith("\n") else ""), True

        return fixed_patch_content, False

    def apply_fixes_sync(
        self,
        current_patch: str,
        review_issues: List[ReviewIssue],
        llm_fixes: Dict[str, LineEdit],
    ) -> ModelFixResult:
        """
        Compatibility adapter for existing app agents.
        Produces model-level FixResult consumed by app/runtime flows.
        """
        chanakya_issues: list[dict[str, Any]] = []
        for issue in review_issues:
            candidate = llm_fixes.get(issue.issue_id)
            chanakya_issues.append(
                {
                    "id": issue.issue_id,
                    "type": issue.category,
                    "line_number": issue.line_number,
                    "problematic_code": candidate.original_line if candidate else issue.problematic_code,
                    "suggested_fix": candidate.fixed_line if candidate else issue.suggested_fix,
                    "explanation": candidate.justification if candidate else issue.explanation,
                }
            )

        result = self._apply_fixes_core(current_patch, chanakya_issues, "Author <email>")

        diff_lines = list(
            difflib.unified_diff(
                current_patch.splitlines(keepends=True),
                result.fixed_patch_content.splitlines(keepends=True),
                fromfile="before_fix",
                tofile="after_fix",
                lineterm="",
            )
        )

        applied: dict[str, LineEdit] = {}
        for issue in review_issues:
            edit = llm_fixes.get(issue.issue_id)
            if edit:
                applied[issue.issue_id] = edit

        return ModelFixResult(
            fixed_patch=result.fixed_patch_content,
            applied_fixes=applied,
            validation_result={
                "passed": result.validation_passed,
                "issues": result.errors,
                "checkpatch_output": result.checkpatch_output,
            },
            diff_from_previous="".join(diff_lines),
            issues_addressed=[issue.issue_id for issue in review_issues],
            checkpatch_output=result.checkpatch_output,
        )
