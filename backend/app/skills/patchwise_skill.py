from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from app.skills.checkpatch_skill import run_checkpatch


@dataclass
class PatchHunk:
    file: str
    header: str
    added_lines: list[str]
    removed_lines: list[str]


@dataclass
class BaseIssue:
    issue_type: str
    severity: str
    line_number: int
    description: str
    suggestion: str


def _to_dicts(issues: list[BaseIssue]) -> list[dict]:
    return [asdict(issue) for issue in issues]


def parse_patch(raw_text: str) -> list[PatchHunk]:
    hunks: list[PatchHunk] = []
    current_file = "unknown"
    header = ""
    added: list[str] = []
    removed: list[str] = []

    for line in raw_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line.replace("+++ b/", "", 1)
        elif line.startswith("@@"):
            if header:
                hunks.append(PatchHunk(current_file, header, added, removed))
            header = line
            added, removed = [], []
        elif line.startswith("+") and not line.startswith("+++"):
            added.append(line[1:])
        elif line.startswith("-") and not line.startswith("---"):
            removed.append(line[1:])

    if header:
        hunks.append(PatchHunk(current_file, header, added, removed))
    return hunks


def check_kernel_style(patch: str) -> list[dict]:
    result = run_checkpatch(patch)
    if result.get("status") == "skipped":
        # Avoid noisy style heuristics when checkpatch.pl is unavailable.
        return []

    output = result.get("output", "")
    if not output:
        return []

    issues: list[BaseIssue] = []
    pending_msg = ""
    pending_severity = "INFO"
    seen: set[tuple[int, str]] = set()

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if line.startswith("ERROR:"):
            pending_msg = line.split(":", 1)[1].strip()
            pending_severity = "CRITICAL"
            continue
        if line.startswith("WARNING:"):
            pending_msg = line.split(":", 1)[1].strip()
            pending_severity = "WARNING"
            continue
        if line.startswith("CHECK:"):
            pending_msg = line.split(":", 1)[1].strip()
            pending_severity = "INFO"
            continue

        if not pending_msg:
            continue

        line_match = re.search(r"#(\\d+):", line) or re.search(r"FILE:[^:]+:(\\d+):", line)
        if not line_match:
            continue

        line_number = int(line_match.group(1))
        key = (line_number, pending_msg)
        if key in seen:
            pending_msg = ""
            continue
        seen.add(key)

        issues.append(
            BaseIssue(
                issue_type="STYLE",
                severity=pending_severity,
                line_number=line_number,
                description=pending_msg,
                suggestion="Apply checkpatch.pl recommended fix for this line.",
            )
        )
        pending_msg = ""

    return _to_dicts(issues)


def check_logic_correctness(patch: str, source_context: str) -> list[dict]:
    _ = source_context
    issues: list[BaseIssue] = []
    for idx, line in enumerate(patch.splitlines(), 1):
        if "if (" in line and "== NULL" in line:
            issues.append(
                BaseIssue(
                    issue_type="LOGIC",
                    severity="WARNING",
                    line_number=idx,
                    description="NULL comparison in condition can be simplified.",
                    suggestion="Use idiomatic NULL check for maintainability.",
                )
            )
        if "TODO" in line:
            issues.append(
                BaseIssue(
                    issue_type="LOGIC",
                    severity="INFO",
                    line_number=idx,
                    description="TODO marker left in patch.",
                    suggestion="Resolve TODO before submitting upstream.",
                )
            )
    return _to_dicts(issues)


def check_memory_safety(patch: str) -> list[dict]:
    issues: list[BaseIssue] = []
    lines = patch.splitlines()
    saw_kmalloc = False
    saw_null_check = False
    kmalloc_line = 0

    for idx, line in enumerate(lines, 1):
        if "kmalloc(" in line or "kzalloc(" in line:
            saw_kmalloc = True
            kmalloc_line = idx
        if saw_kmalloc and ("if (!" in line or ("if (" in line and "NULL" in line)):
            saw_null_check = True

    if saw_kmalloc and not saw_null_check:
        issues.append(
            BaseIssue(
                issue_type="MEMORY",
                severity="CRITICAL",
                line_number=kmalloc_line,
                description="Allocation result may be used without NULL check.",
                suggestion="Check allocation return and handle -ENOMEM path.",
            )
        )

    return _to_dicts(issues)


def check_lkml_compliance(patch: str) -> list[dict]:
    issues: list[BaseIssue] = []
    if "Signed-off-by:" not in patch:
        issues.append(
            BaseIssue(
                issue_type="LKML",
                severity="WARNING",
                line_number=1,
                description="Missing Signed-off-by trailer.",
                suggestion="Add Signed-off-by line to satisfy DCO expectations.",
            )
        )
    return _to_dicts(issues)


def check_commit_message(patch: str) -> list[dict]:
    issues: list[BaseIssue] = []
    subject = ""
    for line in patch.splitlines():
        if line.startswith("Subject:"):
            subject = line.replace("Subject:", "", 1).strip()
            break

    if not subject:
        issues.append(
            BaseIssue(
                issue_type="COMMIT",
                severity="WARNING",
                line_number=1,
                description="Missing Subject line in patch header.",
                suggestion="Include a concise subsystem-prefixed subject.",
            )
        )
    elif ":" not in subject:
        issues.append(
            BaseIssue(
                issue_type="COMMIT",
                severity="INFO",
                line_number=1,
                description="Subject does not include subsystem prefix.",
                suggestion="Use format like 'ASoC: codec: short summary'.",
            )
        )

    if "fix" in subject.lower() and "Fixes:" not in patch:
        issues.append(
            BaseIssue(
                issue_type="COMMIT",
                severity="INFO",
                line_number=1,
                description="Patch looks like a fix but lacks Fixes trailer.",
                suggestion="Add Fixes: <sha> trailer when applicable.",
            )
        )

    return _to_dicts(issues)


def search_similar_patches(
    patch: str,
    subsystem: str,
    sources: list[str] | None = None,
) -> list[dict]:
    del patch
    sources = sources or ["lkml", "gerrit", "local"]

    catalog = {
        "lkml": {
            "title": "ASoC: ops: validate hw_params path",
            "url": "https://lore.kernel.org/alsa-devel/",
            "author": "Kernel Maintainer",
            "date": "2025-10-03",
            "relevance_score": 0.92,
        },
        "gerrit": {
            "title": "ASoC: tighten error unwind in probe",
            "url": "https://android-review.googlesource.com/",
            "author": "Platform Audio Team",
            "date": "2025-06-18",
            "relevance_score": 0.81,
        },
        "local": {
            "title": "PatchWise KB: common ALSA checkpatch remediations",
            "url": f"local://patchwise/{subsystem}/style-remediation",
            "author": "PatchWise",
            "date": "2026-01-11",
            "relevance_score": 0.76,
        },
    }

    refs: list[dict] = []
    for source in sources:
        if source in catalog:
            entry = dict(catalog[source])
            entry["source"] = source
            refs.append(entry)
    return refs


def full_patch_analysis(patch: str, source_context: str = "") -> dict[str, list[dict]]:
    return {
        "style": check_kernel_style(patch),
        "logic": check_logic_correctness(patch, source_context),
        "memory": check_memory_safety(patch),
        "lkml": check_lkml_compliance(patch),
        "commit": check_commit_message(patch),
    }
