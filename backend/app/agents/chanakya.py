from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional

from agents.chanakya_agent import CHANAKYA_ISSUE_FORMAT_PROMPT
from app.agents.state import PatchWiseState
from app.skills.patchwise_skill import full_patch_analysis
from app.skills.search_skill import SearchSkill
from core.llm_factory import get_llm
from core.patchwise_skill import PatchWiseResult, PatchWiseSkill
from agents.version_intelligence import fetch_version_history
from agents.aryabhata_fix_engine import AryabhataFixEngine
from agents.cover_letter_generator import generate_cover_letter_if_missing
from intelligence.cover_letter_reviewer import CoverLetterReviewer
from intelligence.patch_version_intelligence import PatchVersionIntelligence
from models.patch_models import LineEdit, ReviewIssue


CHANAKYA_SYSTEM_PROMPT = """
You are CHANAKYA — Analyst & Patch Engineer for Linux kernel patch review.

YOUR ROLE (CRITICAL — Read carefully):
You are NOT just a reviewer who lists issues for someone else to fix.
You are BOTH the analyst AND the engineer who FIXES what you find.
You behave exactly like the QGenie CLI patchwise workflow:
  1. Analyze the patch thoroughly
  2. Run patchwise tools (checkpatch, ai_code_review, LLMCommitAudit)
  3. DO manual code analysis beyond tool output
  4. FIX every issue you find — in the SAME step
  5. Generate a REAL fixed patch file
  6. Self-validate your fix with checkpatch before submitting

WHAT YOU MUST DO FOR EVERY REVIEW SESSION:

  STEP 1 — PATCH INPUT PROCESSING:
    - Detect patch version (v1, v2, v3...)
    - If versioned: fetch ALL previous versions from lore.kernel.org
    - Parse version history: what was flagged, what was fixed, what was missed
    - Check cover letter: subject, changelog, Link: to previous version, diffstat
    - If cover letter has placeholders → GENERATE REAL CONTENT

  STEP 2 — TOOL ANALYSIS:
    Run in this order:
    a) patchwise --reviews Checkpatch LLMCommitAudit AiCodeReview
       --provider https://qgenie-chat.qualcomm.com/v1
    b) If patchwise fails → fallback to checkpatch.pl directly
    c) Parse ALL tool output into structured issues

  STEP 3 — MANUAL CODE ANALYSIS (CRITICAL — beyond tool output):
    Examine the actual diff carefully:
    - Check function signatures for error propagation (void vs int return)
    - Check callers of modified functions for broken error handling
    - Check header files for stale declarations
    - Check PM runtime patterns (devm_ vs non-devm_ consistency)
    - Check cross-line impact (change on line N affects logic on line M)

  STEP 4 — FIX ALL ISSUES (DO NOT JUST LIST THEM):
    For EACH issue found:
    a) Apply targeted fix to source file or patch hunk
    b) Regenerate clean patch output
    c) Self-validate with checkpatch
    d) Output fixed patch with <<<FIXED_PATCH_START>>> markers

  STEP 5 — COVER LETTER:
    If cover letter has placeholder text OR is missing changelog:
    → GENERATE real cover letter content from patch context
    → Use format: [PATCH v{N} 0/{M}] {subsystem}: {brief description}
    → Include: Changes in v{N} section with REAL changelog
    → Include: Link: https://lore.kernel.org/... to previous version
    → Output as separate <<<COVER_LETTER_START>>> markers
    → Mark as DRAFT — requires user approval before applying

  STEP 6 — STRUCTURED OUTPUT:
    Output MUST include ALL of these for each issue:
    {
      "issue_id": "R{round}_I{num}",
      "type": "STYLE|LOGIC|MEMORY|COMPLIANCE|COMMIT|COVER_LETTER",
      "severity": "BLOCKING|CRITICAL|WARNING|INFO",
      "file": "drivers/.../file.c",
      "line": 42,
      "problematic_code": "bad line",
      "fix_applied": "corrected line",
      "explanation": "why this is wrong",
      "reference": "https://www.kernel.org/doc/html/latest/...",
      "fixed_in_patch": true
    }
"""

pvi = PatchVersionIntelligence()
cover_reviewer = CoverLetterReviewer()
_PATCHWISE_SKILL: PatchWiseSkill | None = None
_PATCHWISE_INIT_ERROR: str | None = None
logger = logging.getLogger("uvicorn.error")


def _ensure_list(state: dict[str, Any], key: str) -> list[Any]:
    value = state.get(key)
    if not isinstance(value, list):
        value = []
        state[key] = value
    return value


COMMON_KERNEL_PATHS = [
    "/local/mnt/workspace/upstream_patches/xo_sd_LPI/linux-next",
    "/local/mnt/workspace/linux-next",
    "/workspace/linux-next",
    "/kernel/linux-next",
    "/tmp/patchwise/sandbox/kernel",
]


def _resolve_kernel_path(source_hint: str, patch_text: str) -> Optional[str]:
    if source_hint and os.path.isdir(source_hint):
        if os.path.exists(os.path.join(source_hint, "scripts/checkpatch.pl")):
            return source_hint

    match = re.search(r"^diff --git a/(.+?) b/", patch_text, re.MULTILINE)
    candidate = match.group(1) if match else ""

    for base in COMMON_KERNEL_PATHS:
        if not os.path.isdir(base):
            continue
        if candidate and os.path.exists(os.path.join(base, candidate)):
            if os.path.exists(os.path.join(base, "scripts/checkpatch.pl")):
                return base
        if os.path.exists(os.path.join(base, "scripts/checkpatch.pl")):
            return base

    return None


def _emit(state: dict[str, Any], payload: dict[str, Any]) -> None:
    callback = state.get("_stream_callback")
    if callable(callback):
        callback(payload)


def _emit_tokens(
    state: dict[str, Any],
    agent: str,
    msg_type: str,
    round_id: int,
    text: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    for token in text.split(" "):
        _emit(
            state,
            {
                "agent": agent,
                "type": msg_type,
                "round": round_id,
                "content": token + " ",
                "metadata": metadata or {},
            },
        )


def _clamp_line(lines: list[str], line_number: int) -> int:
    if not lines:
        return 1
    return max(1, min(line_number, len(lines)))


def _line_context(lines: list[str], line_number: int, radius: int = 5) -> tuple[str, str]:
    line_number = _clamp_line(lines, line_number)
    start = max(1, line_number - radius)
    end = min(len(lines), line_number + radius)
    snippet = "\n".join(lines[start - 1 : end])
    problematic = lines[line_number - 1] if lines else ""
    return snippet, problematic


def _current_file_path(lines: list[str], line_number: int) -> str:
    line_number = _clamp_line(lines, line_number)
    for idx in range(line_number - 1, -1, -1):
        line = lines[idx]
        if line.startswith("+++ b/"):
            return line.replace("+++ b/", "", 1).strip()
    return "COMMIT_MSG" if line_number <= 20 else "unknown"


def _category(bucket: str) -> str:
    mapping = {
        "style": "STYLE",
        "logic": "LOGIC",
        "memory": "MEMORY",
        "lkml": "COMPLIANCE",
        "commit": "COMMIT",
    }
    return mapping.get(bucket, "STYLE")


def _default_fix(problematic: str, issue: dict[str, Any]) -> str:
    suggestion = (issue.get("suggestion") or issue.get("suggested_fix") or "").strip()
    issue_type = issue.get("issue_type", issue.get("type", ""))
    if suggestion and suggestion != problematic:
        return suggestion
    if issue_type == "STYLE":
        return problematic.replace("\t", "    ")
    if issue_type == "LOGIC":
        return problematic.replace("== NULL", "")
    if issue_type == "MEMORY":
        if problematic.strip().startswith("+") or problematic.strip().startswith(" "):
            return problematic
        return "if (!ptr) return -ENOMEM;"
    if issue_type == "COMMIT":
        return "Subject: [PATCH] ASoC: component: short summary"
    if issue_type == "COMPLIANCE":
        return "Signed-off-by: Author <email>"
    return problematic


def _line_at(patch: str, line_number: int) -> str:
    lines = patch.splitlines()
    if not lines:
        return ""
    line_number = max(1, min(line_number, len(lines)))
    return lines[line_number - 1]


def _extract_changed_lines(diff_text: str) -> list[int]:
    changed: list[int] = []
    current_new_line = 0
    for line in (diff_text or "").splitlines():
        hunk_match = re.match(r"^@@ -\\d+(?:,\\d+)? \\+(\\d+)(?:,\\d+)? @@", line)
        if hunk_match:
            current_new_line = int(hunk_match.group(1))
            continue
        if line.startswith("+") and not line.startswith("+++"):
            changed.append(current_new_line)
            current_new_line += 1
            continue
        if line.startswith("-") and not line.startswith("---"):
            continue
        if line.startswith((" ", "\\t")):
            current_new_line += 1
    return sorted(set(changed))


def _default_fixed_line(issue: ReviewIssue, current_patch: str) -> str:
    if issue.suggested_fix:
        return issue.suggested_fix
    problematic = issue.problematic_code or _line_at(current_patch, issue.line_number)
    return _default_fix(problematic, {"issue_type": issue.category})


def _coerce_issue(raw: dict[str, Any], idx: int, round_id: int, patch: str) -> ReviewIssue:
    line_number = int(raw.get("line_number", 1) or 1)
    problematic = raw.get("problematic_code") or _line_at(patch, line_number)
    return ReviewIssue(
        issue_id=raw.get("issue_id", f"R{round_id}_{idx:03d}"),
        category=raw.get("category", raw.get("issue_type", "STYLE")),
        severity=raw.get("severity", "WARNING"),
        line_number=line_number,
        file_path=raw.get("file_path", "unknown"),
        hunk_context=raw.get("hunk_context", ""),
        error_message=raw.get("error_message", raw.get("description", "")),
        problematic_code=problematic,
        suggested_fix=raw.get("suggested_fix", raw.get("suggestion", "")),
        explanation=raw.get("explanation", raw.get("description", "")),
        reference=raw.get("reference"),
        is_recurring=bool(raw.get("is_recurring", raw.get("recurring", False))),
        previous_round=raw.get("previous_round", raw.get("first_seen")),
        round_number=round_id,
    )


def _extract_json(text: str) -> Any | None:
    if not text:
        return None
    candidates = [text]
    first_brace = text.find("{")
    first_bracket = text.find("[")
    idxs = [idx for idx in (first_brace, first_bracket) if idx >= 0]
    if idxs:
        candidates.append(text[min(idxs):])

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except Exception:
            continue
    return None


def _get_patchwise_skill() -> tuple[PatchWiseSkill | None, str | None]:
    global _PATCHWISE_SKILL
    global _PATCHWISE_INIT_ERROR

    if _PATCHWISE_SKILL is not None:
        return _PATCHWISE_SKILL, None
    if _PATCHWISE_INIT_ERROR:
        return None, _PATCHWISE_INIT_ERROR

    try:
        _PATCHWISE_SKILL = PatchWiseSkill()
        return _PATCHWISE_SKILL, None
    except Exception as exc:
        _PATCHWISE_INIT_ERROR = str(exc)
        return None, _PATCHWISE_INIT_ERROR


def _analyses_from_patchwise(pw_result: PatchWiseResult) -> dict[str, list[dict[str, Any]]]:
    analyses: dict[str, list[dict[str, Any]]] = {
        "style": [],
        "logic": [],
        "memory": [],
        "lkml": [],
        "commit": [],
    }

    for issue in pw_result.checkpatch_issues:
        analyses["style"].append(
            {
                "issue_type": "STYLE",
                "severity": issue.get("severity", "WARNING"),
                "line_number": int(issue.get("line_number", 1) or 1),
                "description": issue.get("message", "checkpatch issue"),
                "suggestion": issue.get("suggested_fix", "Apply checkpatch suggested fix."),
            }
        )

    for issue in pw_result.ai_review_issues:
        category = str(issue.get("category", "LOGIC")).upper()
        bucket = {
            "STYLE": "style",
            "LOGIC": "logic",
            "MEMORY": "memory",
            "COMMIT": "commit",
            "COMPLIANCE": "lkml",
        }.get(category, "logic")
        analyses[bucket].append(
            {
                "issue_type": category,
                "severity": issue.get("severity", "WARNING"),
                "line_number": int(issue.get("line_number", 1) or 1),
                "description": issue.get("error_message") or issue.get("message") or "AI review issue",
                "suggestion": issue.get("suggested_fix") or issue.get("suggestion") or "Apply targeted fix.",
            }
        )

    return analyses


def _build_review_prompt(patch_text: str, pw_result: PatchWiseResult, state: PatchWiseState) -> str:
    return f"""You are CHANAKYA, a senior Linux kernel reviewer specializing
in ALSA/ASoC audio subsystem patches for Qualcomm.

You are reviewing Round {state.get('current_round', 1)} of this patch.

PATCHWISE ANALYSIS (from official PatchWise tool via QGenie):
{pw_result.raw_output[:3000]}

CHECKPATCH ISSUES FOUND: {len(pw_result.checkpatch_issues)}
AI REVIEW ISSUES FOUND: {len(pw_result.ai_review_issues)}

FULL PATCH CONTENT:
{patch_text}

PREVIOUS ROUNDS: {len(state.get('review_findings', []))}

TASK:
Return JSON array where each item contains:
- issue_id
- severity (CRITICAL|WARNING|INFO)
- error_message
- suggested_fix
- explanation

Only refine existing issues and improve upstream relevance.
Do not invent unrelated issues.
"""


def _enrich_issues_with_remote_llm(
    state: PatchWiseState,
    structured_issues: list[dict[str, Any]],
    pw_result: PatchWiseResult | None,
) -> tuple[list[dict[str, Any]], str]:
    provider = state.get("llm_provider")
    model = state.get("llm_model")

    try:
        llm = get_llm(model=model, provider=provider, temperature=0.1, streaming=True)
        analysis_mode = f"{provider or 'qgenie'}:{model or 'gpt-4o'}"
    except Exception as exc:
        return structured_issues, f"local ({exc})"

    if not structured_issues:
        return structured_issues, analysis_mode

    payload = [
        {
            "issue_id": issue["issue_id"],
            "category": issue["category"],
            "severity": issue["severity"],
            "line_number": issue["line_number"],
            "file_path": issue["file_path"],
            "error_message": issue["error_message"],
            "problematic_code": issue["problematic_code"],
            "suggested_fix": issue["suggested_fix"],
            "hunk_context": issue["hunk_context"],
        }
        for issue in structured_issues
    ]

    prompt = _build_review_prompt(
        patch_text=state.get("current_patch") or state.get("patch_input", ""),
        pw_result=pw_result or PatchWiseResult(success=False, raw_output=""),
        state=state,
    )
    prompt += f"\n\nISSUES JSON:\n{json.dumps(payload, ensure_ascii=False)}"

    try:
        response = llm.invoke(prompt)
        content = getattr(response, "content", response)
        if isinstance(content, list):
            content = "\n".join(str(item) for item in content)
        parsed = _extract_json(str(content))
    except Exception:
        parsed = None

    if not isinstance(parsed, list):
        return structured_issues, analysis_mode

    by_id = {
        item.get("issue_id"): item
        for item in parsed
        if isinstance(item, dict) and isinstance(item.get("issue_id"), str)
    }

    for issue in structured_issues:
        update = by_id.get(issue["issue_id"])
        if not update:
            continue
        severity = update.get("severity")
        if severity in {"CRITICAL", "WARNING", "INFO"}:
            issue["severity"] = severity
        if isinstance(update.get("error_message"), str) and update["error_message"].strip():
            issue["error_message"] = update["error_message"].strip()
        if isinstance(update.get("suggested_fix"), str) and update["suggested_fix"].strip():
            issue["suggested_fix"] = update["suggested_fix"].strip()
        if isinstance(update.get("explanation"), str) and update["explanation"].strip():
            issue["explanation"] = update["explanation"].strip()

    return structured_issues, analysis_mode


def find_matching_issue(issue: dict[str, Any], prev_issues: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    for prev in prev_issues:
        same_type = prev.get("category") == issue.get("category")
        same_problem = prev.get("problematic_code", "").strip() == issue.get("problematic_code", "").strip()
        near_line = abs(int(prev.get("line_number", 0) or 0) - int(issue.get("line_number", 0) or 0)) <= 1
        if same_type and (same_problem or near_line):
            return prev
    return None


def check_fix_attempted(issue: dict[str, Any], changes_made: list[dict[str, Any]]) -> bool:
    for change in changes_made:
        type_match = (change.get("issue_type") == issue.get("category")) or (
            change.get("issue_type") == issue.get("type")
        )
        near_line = abs(int(change.get("line", 0) or 0) - int(issue.get("line_number", 0) or 0)) <= 2
        if type_match and near_line:
            return True
    return False


def detect_fix_failure_reason(issue: dict[str, Any], prev_fix: Optional[dict[str, Any]]) -> str:
    if not prev_fix:
        return "No previous fix payload available"
    if not prev_fix.get("validation_passed", True):
        return "Previous fix attempt failed validation"
    return f"Prior change did not resolve the issue at line {issue.get('line_number', 'unknown')}"


def _extract_cover_letter_and_series(patch_text: str) -> tuple[Optional[str], list[str]]:
    import re

    cover_letter = None
    if "Subject:" in patch_text and " 0/" in patch_text and "[PATCH" in patch_text:
        cover_letter = patch_text

    patch_subjects: list[str] = []
    for line in patch_text.splitlines():
        if line.startswith("Subject:") and "[PATCH" in line and re.search(r"\[PATCH[^\]]*\s+\d+/\d+\]", line):
            patch_subjects.append(line)

    if not patch_subjects:
        return cover_letter, [patch_text]
    return cover_letter, patch_subjects


async def _run_version_pre_review(state: PatchWiseState, round_id: int) -> list[dict[str, Any]]:
    session_id = state.get("session_id", "")
    patch_text = state.get("current_patch") or state.get("patch_input", "")

    _emit_tokens(state, "chanakya", "thinking", round_id, "Detecting patch version and prior review history.")

    lore_list = "alsa-devel"
    subsystem_text = str(state.get("subsystem", "")).lower()
    if "asoc" in subsystem_text or "alsa" in subsystem_text:
        lore_list = "alsa-devel"
    input_url = state.get("input_url") or state.get("lore_url")
    robust_history = await fetch_version_history(
        patch_content=patch_text,
        input_url=input_url,
        subsystem=lore_list,
    )

    if robust_history.get("found"):
        reviewer_comments = robust_history.get("reviewer_comments", [])
        version_number = robust_history.get("version", 1)
        _emit(
            state,
            {
                "agent": "chanakya",
                "type": "version_history",
                "round": round_id,
                "content": (
                    f"Version history loaded: {len(reviewer_comments)} reviewer comment(s) "
                    f"for v{version_number} chain."
                ),
                "metadata": {
                    "latest_version": version_number,
                    "unaddressed_count": len(reviewer_comments),
                    "addressed_count": 0,
                    "maintainers": [
                        c.get("author", "")
                        for c in reviewer_comments
                        if c.get("is_maintainer")
                    ],
                    "prev_version_url": robust_history.get("prev_version_url"),
                },
            },
        )
        state["version_chain"] = {
            "latest_version": version_number,
            "maintainers": [
                c.get("author", "")
                for c in reviewer_comments
                if c.get("is_maintainer")
            ],
            "unaddressed_count": len(reviewer_comments),
            "prev_version_url": robust_history.get("prev_version_url"),
        }
        return [
            {
                "issue_type": "COMPLIANCE",
                "severity": "INFO",
                "line_number": 1,
                "description": f"Unaddressed review feedback from {comment.get('author', 'reviewer')}",
                "suggestion": "Address reviewer feedback in this version or explain rationale in cover letter.",
                "explanation": str(comment.get("body", ""))[:500],
                "reviewer_name": comment.get("author", ""),
                "reviewer_email": comment.get("author", ""),
                "reviewer_type": "MAINTAINER" if comment.get("is_maintainer") else "COMMUNITY",
                "message_id": "",
            }
            for comment in reviewer_comments
        ]

    if robust_history.get("degrade_message"):
        _emit(
            state,
            {
                "agent": "chanakya",
                "type": "info",
                "round": round_id,
                "content": robust_history["degrade_message"],
                "metadata": {"ask_user": bool(robust_history.get("ask_user"))},
            },
        )

    chain = await pvi.analyze_patch_version(patch_text, session_id)
    if not chain:
        _emit(
            state,
            {
                "agent": "chanakya",
                "type": "info",
                "round": round_id,
                "content": "No previous version history found. Reviewing patch standalone.",
            },
        )
        return []

    _emit(
        state,
        {
            "agent": "chanakya",
            "type": "version_history",
            "round": round_id,
            "content": (
                f"Detected v{chain.latest_version}; found {len(chain.unaddressed_comments)} "
                "unaddressed prior comments"
            ),
            "metadata": {
                "latest_version": chain.latest_version,
                "unaddressed_count": len(chain.unaddressed_comments),
                "addressed_count": len(chain.addressed_comments),
                "maintainers": chain.maintainers,
            },
        },
    )

    version_issues: list[dict[str, Any]] = []
    for comment in chain.unaddressed_comments:
        version_issues.append(
            {
                "issue_type": "COMPLIANCE",
                "severity": "CRITICAL" if comment.reviewer_type == "MAINTAINER" else "INFO",
                "line_number": 1,
                "description": f"Unaddressed review feedback from {comment.reviewer_name}",
                "suggestion": pvi.generate_suggested_reply(comment, fix_applied=False),
                "explanation": comment.comment_text[:500],
                "reviewer_name": comment.reviewer_name,
                "reviewer_email": comment.reviewer_email,
                "reviewer_type": comment.reviewer_type,
                "message_id": comment.message_id,
            }
        )

    state["version_chain"] = {
        "latest_version": chain.latest_version,
        "maintainers": chain.maintainers,
        "unaddressed_count": len(chain.unaddressed_comments),
    }
    return version_issues


async def chanakya_review_node(state: PatchWiseState) -> PatchWiseState:
    round_id = state.get("current_round", 1)
    patch_text = state.get("current_patch") or state.get("patch_input", "")
    source_context = state.get("source_path", "")
    resolved_kernel_path = _resolve_kernel_path(source_context, patch_text)
    if resolved_kernel_path and resolved_kernel_path != source_context:
        state["source_path"] = resolved_kernel_path
    source_context = resolved_kernel_path or source_context
    patch_lines = patch_text.splitlines()

    hint = state.get("interrupt_hint")
    thinking = "Analyzing with PatchWise (checkpatch + ai_code_review) and QGenie deep review."
    if hint:
        thinking += f" Interrupt hint received: {hint}."
    _emit_tokens(state, "chanakya", "thinking", round_id, thinking)

    patchwise_status = {"used": False, "success": False, "error": None}
    patchwise_result: PatchWiseResult | None = None

    skill, skill_error = _get_patchwise_skill()
    if skill:
        try:
            if source_context and not os.path.isdir(source_context):
                _emit(
                    state,
                    {
                        "agent": "chanakya",
                        "type": "info",
                        "round": round_id,
                        "content": (
                            f"Kernel source path not found ({source_context}). "
                            "Proceeding with PatchWise fallback context."
                        ),
                    },
                )
            patchwise_result = skill.review_patch_file(
                patch_content=patch_text,
                kernel_path=source_context if os.path.isdir(source_context) else None,
                subsystem=state.get("subsystem", "sound/soc"),
            )
            patchwise_status = {
                "used": True,
                "success": bool(patchwise_result.success),
                "error": patchwise_result.error,
            }
        except Exception as exc:
            patchwise_status = {"used": True, "success": False, "error": str(exc)}
    else:
        patchwise_status = {"used": False, "success": False, "error": skill_error}

    if patchwise_result and patchwise_result.success and patchwise_result.issues:
        analyses = _analyses_from_patchwise(patchwise_result)
    else:
        analyses = full_patch_analysis(patch_text, source_context)

    version_issues = await _run_version_pre_review(state, round_id)
    similar_refs = SearchSkill().search(
        patch_text,
        subsystem=state.get("subsystem", "alsa-asoc"),
        sources=["lkml", "gerrit", "local"],
    )

    cover_letter, patch_series = _extract_cover_letter_and_series(patch_text)
    cover_issues = cover_reviewer.review(cover_letter, patch_series)
    if cover_issues:
        _emit(
            state,
            {
                "agent": "chanakya",
                "type": "cover_letter_review",
                "round": round_id,
                "content": f"Cover-letter review found {len(cover_issues)} issue(s).",
                "metadata": {
                    "issue_count": len(cover_issues),
                    "template": cover_reviewer.generate_cover_letter_template(patch_series),
                },
            },
        )

    structured_issues: list[dict[str, Any]] = []
    issue_counter = 1

    def append_issue(raw_issue: dict[str, Any], category: str) -> None:
        nonlocal issue_counter
        line_number = int(raw_issue.get("line_number", 1) or 1)
        hunk_context, problematic = _line_context(patch_lines, line_number)
        file_path = _current_file_path(patch_lines, line_number)
        issue_id = f"R{round_id}_{issue_counter:03d}"
        issue_counter += 1

        issue = {
            "issue_id": issue_id,
            "category": category,
            "severity": raw_issue.get("severity", "WARNING"),
            "line_number": line_number,
            "file_path": file_path,
            "hunk_context": hunk_context,
            "error_message": raw_issue.get("description", ""),
            "problematic_code": problematic,
            "suggested_fix": _default_fix(problematic, raw_issue),
            "explanation": (
                f"{raw_issue.get('description', '')}. "
                f"Upstream expectation: {raw_issue.get('suggestion', 'apply canonical kernel style and logic fixes')}."
            ),
            "reference": (
                "https://www.kernel.org/doc/html/latest/process/submitting-patches.html"
                if category in {"COMMIT", "COMPLIANCE"}
                else None
            ),
            "is_recurring": False,
            "previous_round": None,
            "first_seen_round": round_id,
            "round_number": round_id,
            "similar_patch_refs": similar_refs[:2],
        }

        for key in ["reviewer_name", "reviewer_email", "reviewer_type", "message_id"]:
            if raw_issue.get(key):
                issue[key] = raw_issue[key]

        structured_issues.append(issue)

    for bucket, items in analyses.items():
        category = _category(bucket)
        for raw in items:
            append_issue(raw, category)

    for raw in cover_issues:
        append_issue(raw, "COMPLIANCE")

    for raw in version_issues:
        append_issue(raw, "COMPLIANCE")

    prev_issues = state.get("previous_round_issues", [])
    fix_history = state.get("fix_history", [])
    prev_fix = fix_history[-1] if fix_history else None

    for issue in structured_issues:
        matching_prev = find_matching_issue(issue, prev_issues)
        if not matching_prev:
            continue

        issue["is_recurring"] = True
        issue["previous_round"] = matching_prev.get("first_seen_round", round_id - 1)
        issue["first_seen_round"] = issue["previous_round"]

        attempted = check_fix_attempted(issue, prev_fix.get("changes_made", []) if isinstance(prev_fix, dict) else [])
        if attempted:
            issue["fix_attempted"] = True
            issue["fix_failed_reason"] = detect_fix_failure_reason(issue, prev_fix)
        else:
            issue["missed_fix"] = True

        if issue["severity"] == "INFO":
            issue["severity"] = "WARNING"

    state["previous_round_issues"] = [dict(item) for item in structured_issues]

    structured_issues, analysis_mode = _enrich_issues_with_remote_llm(
        state=state,
        structured_issues=structured_issues,
        pw_result=patchwise_result,
    )

    review_issues = [
        _coerce_issue(issue, idx + 1, round_id, patch_text)
        for idx, issue in enumerate(structured_issues)
    ]
    llm_fixes: dict[str, LineEdit] = {}
    for issue in review_issues:
        fixed_line = issue.suggested_fix or _default_fixed_line(issue, patch_text)
        llm_fixes[issue.issue_id] = LineEdit(
            line_number=issue.line_number,
            original_line=issue.problematic_code or _line_at(patch_text, issue.line_number),
            fixed_line=fixed_line,
            issue_id=issue.issue_id,
            category=issue.category,
            justification=issue.explanation or "Applied targeted upstream-safe correction.",
        )

    fix_engine = AryabhataFixEngine()
    fix_result = None
    fixed_patch = patch_text
    if review_issues:
        fix_result = fix_engine.apply_fixes_sync(
            current_patch=patch_text,
            review_issues=review_issues,
            llm_fixes=llm_fixes,
        )
        fixed_patch = fix_result.fixed_patch
        state["current_patch"] = fixed_patch
        state["current_fixed_patch"] = fixed_patch

    cover_letter_draft = None
    if cover_issues:
        state["patches"] = [patch_text]
        cover_letter_draft = await generate_cover_letter_if_missing(
            state=state,
            llm=None,
            cover_letter_issues=cover_issues,
        )
        if cover_letter_draft:
            state["cover_letter_draft"] = cover_letter_draft
            state["cover_letter_approved"] = False
            logger.info("cover_letter fixed PLACEHOLDER_USE=0")
            _emit(
                state,
                {
                    "agent": "chanakya",
                    "type": "cover_letter_draft",
                    "round": round_id,
                    "content": cover_letter_draft,
                    "metadata": {"draft": True},
                },
            )

    applied = fix_result.applied_fixes if fix_result else {}
    for issue in structured_issues:
        issue_id = issue.get("issue_id")
        edit = applied.get(issue_id) or llm_fixes.get(issue_id)
        issue["type"] = issue.get("category")
        issue["fix_applied"] = edit.fixed_line if edit else ""
        issue["fixed_in_patch"] = bool(edit)

    for issue in structured_issues:
        _emit(
            state,
            {
                "agent": "chanakya",
                "type": "finding",
                "round": round_id,
                "content": issue["error_message"],
                "metadata": {
                    "issue_type": issue["category"],
                    "severity": issue["severity"],
                    "line_number": issue["line_number"],
                    "issue_id": issue["issue_id"],
                    "recurring": issue["is_recurring"],
                    "first_seen": issue["first_seen_round"],
                    "missed_fix": issue.get("missed_fix", False),
                    "fix_attempted": issue.get("fix_attempted", False),
                    "fix_failed_reason": issue.get("fix_failed_reason"),
                    "analysis_mode": analysis_mode,
                    "patchwise": patchwise_status,
                    "issue": issue,
                },
            },
        )

    for ref in similar_refs[:3]:
        _emit(
            state,
            {
                "agent": "chanakya",
                "type": "similar_patch",
                "round": round_id,
                "content": ref.get("title", ""),
                "metadata": ref,
            },
        )

    issue_count = len(structured_issues)
    quality_score = max(0.0, 100.0 - float(issue_count * 14))
    verdict = "PENDING"

    round_payload = {
        "round": round_id,
        "issues": structured_issues,
        "findings": structured_issues,
        "summary": f"Found {issue_count} issue(s).",
        "quality_score": quality_score,
        "analysis_mode": analysis_mode,
        "patchwise": patchwise_status,
        "fixed_patch": fixed_patch,
        "validation": fix_result.validation_result if fix_result else None,
    }

    state["latest_review"] = round_payload
    _ensure_list(state, "review_findings").append(round_payload)
    _ensure_list(state, "similar_patches").extend(similar_refs)
    _ensure_list(state, "conversation_log").append(
        {
            "round": round_id,
            "agent": "chanakya",
            "message": f"Review complete. {issue_count} issue(s).",
            "findings": structured_issues,
        }
    )

    fix_summary: list[dict[str, Any]] = []
    changes_made: list[dict[str, Any]] = []
    for issue in review_issues:
        edit = applied.get(issue.issue_id) or llm_fixes.get(issue.issue_id)
        fix_summary.append(
            {
                "issue_id": issue.issue_id,
                "category": issue.category,
                "line": issue.line_number,
                "problem": issue.error_message,
                "fix": edit.fixed_line if edit else issue.suggested_fix,
                "status": "FIXED" if edit else "SKIPPED",
            }
        )
        if edit:
            changes_made.append(
                {
                    "issue_id": issue.issue_id,
                    "issue_type": issue.category,
                    "line": issue.line_number,
                    "original": edit.original_line,
                    "fixed": edit.fixed_line,
                    "reason": edit.justification,
                }
            )

    marked_patch_main = (
        "<<<FIXED_PATCH_START>>>\n"
        f"{fixed_patch.rstrip()}\n"
        "<<<FIXED_PATCH_END>>>"
    )
    marked_patch = marked_patch_main
    if cover_letter_draft:
        marked_patch = (
            "<<<COVER_LETTER_START>>>\n"
            f"{cover_letter_draft.rstrip()}\n"
            "<<<COVER_LETTER_END>>>\n\n"
            f"{marked_patch_main}"
        )

    diff_from_previous = fix_result.diff_from_previous if fix_result else ""
    changed_lines = _extract_changed_lines(diff_from_previous)

    _emit(
        state,
        {
            "agent": "chanakya",
            "type": "fix_complete",
            "round": round_id,
            "content": marked_patch,
            "fix_summary": fix_summary,
            "changes_made": changes_made,
            "diff_from_previous": diff_from_previous,
            "fixed_patch": fixed_patch,
            "original_patch": patch_text,
            "checkpatch_output": (fix_result.validation_result.get("checkpatch_output") if fix_result else ""),
            "validation_passed": bool(fix_result.validation_result.get("passed", False)) if fix_result else False,
            "patch_marker_start": "<<<FIXED_PATCH_START>>>",
            "patch_marker_end": "<<<FIXED_PATCH_END>>>",
            "marked_patch": marked_patch,
            "changed_lines": changed_lines,
            "requires_approval": bool(cover_letter_draft),
            "cover_letter_draft": cover_letter_draft,
        },
    )
    logger.info("FIXED_PATCH_START emitted by CHANAKYA")

    _ensure_list(state, "fix_history").append(
        {
            "round": round_id,
            "fixes_applied": len([f for f in fix_summary if f.get("status") == "FIXED"]),
            "changes_made": changes_made,
            "diff": diff_from_previous,
            "validation_passed": bool(fix_result.validation_result.get("passed", False)) if fix_result else False,
        }
    )
    _ensure_list(state, "fix_attempts").append(
        {
            "round": round_id,
            "fixes": fix_summary,
            "changes_made": changes_made,
            "summary": f"Applied {len([f for f in fix_summary if f.get('status') == 'FIXED'])} fix(es).",
            "diff_from_previous": diff_from_previous,
            "fixed_patch": fixed_patch,
            "original_patch": patch_text,
            "validation_passed": bool(fix_result.validation_result.get("passed", False)) if fix_result else False,
            "patch_marker_start": "<<<FIXED_PATCH_START>>>",
            "patch_marker_end": "<<<FIXED_PATCH_END>>>",
        }
    )

    state["quality_score"] = quality_score
    state["verdict"] = verdict

    state["interrupt_hint"] = None
    return state
