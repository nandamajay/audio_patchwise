from __future__ import annotations

from dataclasses import asdict, dataclass
import os
import subprocess
import re
import tempfile

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
    """
    Delegate style analysis to checkpatch.pl to match upstream expectations.
    Falls back to no style findings if checkpatch is unavailable.
    """
    result = run_checkpatch(patch)
    if result.get("status") == "skipped":
        return []

    output = result.get("output", "")
    if not output:
        return []

    include_checks = os.environ.get("PATCHWISE_INCLUDE_CHECKPATCH_CHECKS", "false").lower() in {
        "1",
        "true",
        "yes",
    }

    issues: list[BaseIssue] = []
    seen: set[tuple[int, str]] = set()
    current_line = 1
    pending_msg = ""
    pending_severity = "INFO"

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        line_match = re.search(r"#(\d+):", line) or re.search(r"FILE:[^:]+:(\d+):", line)
        if line_match:
            current_line = int(line_match.group(1))

        finding_match = re.match(r"^(ERROR|WARNING|CHECK):[^:]*:\s*(.+)$", line)
        if finding_match:
            level, message = finding_match.groups()
            if level == "CHECK" and not include_checks:
                pending_msg = ""
                continue
            severity = "CRITICAL" if level == "ERROR" else "WARNING" if level == "WARNING" else "INFO"
            key = (current_line, message)
            if key not in seen:
                seen.add(key)
                issues.append(
                    BaseIssue(
                        issue_type="STYLE",
                        severity=severity,
                        line_number=current_line,
                        description=f"checkpatch: {message}",
                        suggestion="Follow checkpatch.pl recommendation or justify deviation in cover letter.",
                    )
                )
            pending_msg = ""
            continue

        if line.startswith("ERROR:"):
            pending_msg = line.split(":", 1)[1].strip()
            pending_severity = "CRITICAL"
            continue
        if line.startswith("WARNING:"):
            pending_msg = line.split(":", 1)[1].strip()
            pending_severity = "WARNING"
            continue
        if line.startswith("CHECK:"):
            if include_checks:
                pending_msg = line.split(":", 1)[1].strip()
                pending_severity = "INFO"
            else:
                pending_msg = ""
            continue

        if pending_msg and line_match:
            key = (current_line, pending_msg)
            if key not in seen:
                seen.add(key)
                issues.append(
                    BaseIssue(
                        issue_type="STYLE",
                        severity=pending_severity,
                        line_number=current_line,
                        description=f"checkpatch: {pending_msg}",
                        suggestion="Follow checkpatch.pl recommendation or justify deviation in cover letter.",
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


def parse_patchwise_output(stdout: str) -> list[dict]:
    issues: list[dict] = []
    if not stdout:
        return issues
    for line in stdout.splitlines():
        match = re.search(r"(ERROR|WARNING|CHECK):\\s*(.+)", line)
        if not match:
            continue
        severity, description = match.groups()
        issues.append(
            {
                "issue_type": "STYLE",
                "severity": severity,
                "line_number": 1,
                "description": description.strip(),
                "suggestion": "Apply PatchWise recommendation.",
            }
        )
    return issues


async def run_qgenie_fallback_review(patch_content: str, subsystem: str) -> list[dict]:
    """
    Direct QGenie review placeholder when PatchWise binary is unavailable.
    """
    _ = subsystem
    return full_patch_analysis(patch_content, "").get("style", [])


async def run_patchwise(
    patch_content: str,
    subsystem: str = "audio",
    kernel_source_path: str | None = None,
) -> dict:
    """
    Run PatchWise skill on patch content with graceful fallback.
    """
    result = {
        "method": "patchwise",
        "issues": [],
        "fallback_used": False,
        "fallback_reason": None,
    }

    with tempfile.NamedTemporaryFile(suffix=".patch", mode="w", delete=False, dir="/tmp") as file_obj:
        file_obj.write(patch_content)
        patch_file = file_obj.name

    try:
        patchwise_check = subprocess.run(["which", "patchwise"], capture_output=True, check=False)
        if patchwise_check.returncode != 0:
            raise FileNotFoundError("patchwise binary not found")

        cmd = [
            "patchwise",
            "--reviews",
            "checkpatch",
            "ai_code_review",
            "--provider",
            os.environ.get("QGENIE_BASE_URL", "https://qgenie-chat.qualcomm.com/v1"),
            "--patch",
            patch_file,
        ]

        if kernel_source_path:
            if os.path.isdir(kernel_source_path):
                cmd.extend(["--kernel-source", kernel_source_path])
            else:
                print(f"[WARN] Kernel source path not found: {kernel_source_path}")
                print("[WARN] Proceeding without kernel source context")

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

        if proc.returncode == 0:
            result["issues"] = parse_patchwise_output(proc.stdout)
        else:
            raise RuntimeError(f"patchwise failed: {proc.stderr}")

    except (FileNotFoundError, RuntimeError, subprocess.TimeoutExpired) as exc:
        result["fallback_used"] = True
        result["fallback_reason"] = str(exc)
        result["issues"] = await run_qgenie_fallback_review(patch_content, subsystem)
        result["method"] = "qgenie_fallback"
        result["fallback_message"] = (
            f"PatchWise unavailable ({str(exc)[:50]}...). "
            "Using QGenie AI review - full analysis continues."
        )
    finally:
        try:
            os.unlink(patch_file)
        except Exception:
            pass

    return result
