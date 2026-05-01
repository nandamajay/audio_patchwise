from __future__ import annotations

import json
from typing import Any, Optional

from agents.chanakya_agent import CHANAKYA_ISSUE_FORMAT_PROMPT
from agents.impact_analyzer import impact_analyzer
from agents.shared.negotiation_bus import check_for_deadlock
from app.agents.state import PatchWiseState
from app.skills.patchwise_skill import full_patch_analysis
from app.skills.search_skill import SearchSkill
from agents.chanakya.version_intelligence import PatchVersionIntelligence
from core.llm_factory import get_llm
from core.patchwise_skill import PatchWiseResult, PatchWiseSkill
from intelligence.cover_letter_reviewer import CoverLetterReviewer


CHANAKYA_SYSTEM_PROMPT = """
You are CHANAKYA — the Reviewer Agent in the PatchWise A2A system.
You review kernel patches for the audio subsystem (ALSA/ASoC).

ABSOLUTE OUTPUT RULES:

RULE 1 — EVERY ISSUE MUST HAVE ALL FIELDS:
Output issues as structured JSON array ONLY:

{
  "issues": [
    {
      "id": "issue_001",
      "type": "STYLE|LOGIC|MEMORY|COMMIT|COMPLIANCE",
      "severity": "CRITICAL|WARNING|INFO",
      "line_number": 42,
      "file_path": "sound/soc/qcom/audio-driver.c",
      "problematic_code": "return -EINVAL;",
      "suggested_fix": "return -ENOMEM;",
      "explanation": "Wrong error code — ENOMEM for allocation failure per kernel convention",
      "reference": "https://lore.kernel.org/...",
      "confidence": 0.95,
      "checkpatch_raw": "ERROR: return type mismatch"
    }
  ],
  "round_summary": "Found 3 issues — 1 CRITICAL, 2 WARNING",
  "lgtm": false,
  "surgical_focus": [42, 43, 50]
}

RULE 2 — NEVER OUTPUT GENERIC TEXT.
Always output specific findings per issue.

RULE 3 — FOR SURGICAL RE-REVIEW:
When reviewing touched lines only, explicitly state:
"SURGICAL REVIEW — checking lines [n1, n2, n3] only based on ARYABHATA's changes"
Only flag issues in the surgical scope lines.

RULE 4 — SIMILAR PATCH SEARCH:
Always search KB for similar patches and include reference URLs when found.

RULE 5 — RECURRING ISSUE DETECTION:
If an issue was flagged in a previous round and still exists, set:
"recurring_from_round": <round_number>
and explain that ARYABHATA's previous fix did not resolve it.
""" + "\n\n" + CHANAKYA_ISSUE_FORMAT_PROMPT

cover_reviewer = CoverLetterReviewer()
_PATCHWISE_SKILL: PatchWiseSkill | None = None
_PATCHWISE_INIT_ERROR: str | None = None


def _ensure_list(state: dict[str, Any], key: str) -> list[Any]:
    value = state.get(key)
    if not isinstance(value, list):
        value = []
        state[key] = value
    return value


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
    review_type = state.get("review_type", "FULL")
    scope_lines = state.get("review_scope_lines") or []
    scope_text = (
        f"SURGICAL REVIEW — checking lines {scope_lines} only based on ARYABHATA's changes."
        if review_type == "SURGICAL" and scope_lines
        else "FULL REVIEW over entire patch."
    )
    return f"""You are CHANAKYA, a senior Linux kernel reviewer specializing
in ALSA/ASoC audio subsystem patches for Qualcomm.

You are reviewing Round {state.get('current_round', 1)} of this patch.
{scope_text}

PATCHWISE ANALYSIS (from official PatchWise tool via QGenie):
{pw_result.raw_output[:3000]}

CHECKPATCH ISSUES FOUND: {len(pw_result.checkpatch_issues)}
AI REVIEW ISSUES FOUND: {len(pw_result.ai_review_issues)}

FULL PATCH CONTENT:
{patch_text}

PREVIOUS ROUNDS: {len(state.get('review_findings', []))}

TASK:
Return STRICT JSON OBJECT only:
{{
  "issues": [{{ ... }}],
  "round_summary": "string",
  "lgtm": false,
  "surgical_focus": [{",".join(str(item) for item in scope_lines[:20]) if scope_lines else "1,2,3"}]
}}

Each issue must include:
- id
- type (STYLE|LOGIC|MEMORY|COMMIT|COMPLIANCE)
- severity (CRITICAL|WARNING|INFO)
- line_number
- file_path
- problematic_code
- suggested_fix
- explanation
- reference
- confidence
- checkpatch_raw

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

    parsed_issues: list[dict[str, Any]] = []
    if isinstance(parsed, dict):
        maybe = parsed.get("issues")
        if isinstance(maybe, list):
            parsed_issues = [item for item in maybe if isinstance(item, dict)]
    elif isinstance(parsed, list):
        parsed_issues = [item for item in parsed if isinstance(item, dict)]
    if not parsed_issues:
        return structured_issues, analysis_mode

    by_id: dict[str, dict[str, Any]] = {}
    for item in parsed_issues:
        issue_id = item.get("issue_id") or item.get("id")
        if isinstance(issue_id, str) and issue_id:
            by_id[issue_id] = item

    for issue in structured_issues:
        update = by_id.get(issue["issue_id"]) or by_id.get(issue.get("id", ""))
        if not update:
            continue
        severity = update.get("severity")
        if severity in {"CRITICAL", "WARNING", "INFO"}:
            issue["severity"] = severity
        issue_type = update.get("type") or update.get("category")
        if issue_type in {"STYLE", "LOGIC", "MEMORY", "COMMIT", "COMPLIANCE"}:
            issue["category"] = issue_type
            issue["type"] = issue_type
        if isinstance(update.get("error_message"), str) and update["error_message"].strip():
            issue["error_message"] = update["error_message"].strip()
        elif isinstance(update.get("problematic_code"), str) and update["problematic_code"].strip():
            issue["problematic_code"] = update["problematic_code"].strip()
        if isinstance(update.get("suggested_fix"), str) and update["suggested_fix"].strip():
            issue["suggested_fix"] = update["suggested_fix"].strip()
        if isinstance(update.get("explanation"), str) and update["explanation"].strip():
            issue["explanation"] = update["explanation"].strip()
        if isinstance(update.get("reference"), str):
            issue["reference"] = update["reference"].strip() or issue.get("reference")
        confidence = update.get("confidence")
        if isinstance(confidence, (int, float)):
            issue["confidence"] = max(0.0, min(1.0, float(confidence)))
        if isinstance(update.get("checkpatch_raw"), str):
            issue["checkpatch_raw"] = update["checkpatch_raw"]

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
    session_id = state["session_id"]
    patch_content = state.get("current_patch") or state.get("patch_input", "")
    user_link = state.get("lore_link") or state.get("gerrit_link") or ""

    _emit(
        state,
        {
            "agent": "chanakya",
            "type": "thinking",
            "round": round_id,
            "content": (
                "Analyzing with PatchWise (checkpatch + ai_code_review) and QGenie deep review. "
                "Detecting patch version and prior review history..."
            ),
            "metadata": {},
        },
    )

    vi = PatchVersionIntelligence()
    chain = await vi.get_version_chain(
        patch_content=patch_content,
        user_provided_link=user_link,
        session_id=session_id,
    )

    if chain.fetch_status == "NO_HISTORY":
        _emit(
            state,
            {
                "agent": "chanakya",
                "type": "info",
                "round": round_id,
                "content": "v1 patch detected - no prior version history. Reviewing standalone.",
                "metadata": {},
            },
        )
    elif chain.fetch_status == "DEGRADED":
        if chain.found_via == "not_found":
            _emit(
                state,
                {
                    "agent": "chanakya",
                    "type": "needs_input",
                    "round": round_id,
                    "content": "",
                    "metadata": {
                        "message": (
                            f"This appears to be v{chain.current_version} but no previous "
                            f"version link was found. Searched by subject - not found. "
                            f"Please provide the lore.kernel.org link to v{chain.current_version-1} "
                            f"for complete context. Proceeding with standalone review."
                        ),
                        "type": "version_link_needed",
                        "version": chain.current_version - 1,
                    },
                },
            )
        else:
            _emit(
                state,
                {
                    "agent": "chanakya",
                    "type": "warning",
                    "round": round_id,
                    "content": (
                        f"lore.kernel.org temporarily unreachable. "
                        f"Reviewing v{chain.current_version} standalone (reduced context)."
                    ),
                    "metadata": {},
                },
            )
    elif chain.fetch_status == "SUCCESS":
        _emit(
            state,
            {
                "agent": "chanakya",
                "type": "version_history",
                "round": round_id,
                "content": "",
                "metadata": {
                    "message": (
                        f"Version history loaded: {len(chain.versions)} previous version(s)\n"
                        f"{len(chain.reviewer_comments)} reviewer comments found\n"
                        f"{len(chain.addressed_comments)} addressed in this version\n"
                        f"{len(chain.unaddressed_comments)} unaddressed - require attention"
                    ),
                    "unaddressed": [
                        {
                            "author": c.author,
                            "role": c.role,
                            "preview": c.body[:100],
                            "suggested_reply": c.suggested_reply,
                            "reply_quality": c.reply_quality,
                        }
                        for c in chain.unaddressed_comments
                    ],
                },
            },
        )

    state["version_chain"] = chain
    state["version_intelligence_complete"] = True

    version_issues: list[dict[str, Any]] = []
    for comment in chain.unaddressed_comments:
        version_issues.append(
            {
                "issue_type": "COMPLIANCE",
                "severity": "CRITICAL" if comment.role == "MAINTAINER" else "INFO",
                "line_number": 1,
                "description": f"Unaddressed review feedback from {comment.author}",
                "suggestion": comment.suggested_reply,
                "explanation": comment.body[:500],
                "reviewer_name": comment.author,
                "reviewer_email": comment.email,
                "reviewer_type": comment.role,
                "message_id": comment.message_id,
            }
        )

    return version_issues


async def chanakya_review_node(state: PatchWiseState) -> PatchWiseState:
    round_id = state.get("current_round", 1)
    patch_text = state.get("current_patch") or state.get("patch_input", "")
    source_context = state.get("source_path", "")
    patch_lines = patch_text.splitlines()
    touched_lines: list[int] = []
    for value in state.get("touched_lines", []) or []:
        try:
            line = int(value)
        except Exception:
            continue
        if line > 0:
            touched_lines.append(line)
    touched_lines = sorted(set(touched_lines))
    review_type = "SURGICAL" if round_id > 1 and touched_lines else "FULL"
    review_scope_lines: list[int] = []
    if review_type == "SURGICAL":
        impact = await impact_analyzer.get_impact_radius(
            changed_lines=touched_lines,
            patch_content=patch_text,
        )
        review_scope_lines = sorted(impact.full_scope)
        _emit(
            state,
            {
                "agent": "system",
                "type": "impact_map_update",
                "round": round_id,
                "content": "Impact analysis updated for touched lines.",
                "metadata": {
                    "session_id": state.get("session_id", ""),
                    "touched_lines": touched_lines,
                    "impact_radius": {
                        "direct": sorted(impact.direct_lines),
                        "downstream": sorted(impact.downstream_lines),
                        "upstream": sorted(impact.upstream_lines),
                        "cross_file": [item.__dict__ for item in impact.cross_file_impacts],
                        "impact_chain": list(impact.impact_chain),
                    },
                },
            },
        )
        _emit(
            state,
            {
                "agent": "chanakya",
                "type": "surgical_review_start",
                "round": round_id,
                "content": (
                    f"SURGICAL REVIEW — checking lines {review_scope_lines} only "
                    "based on ARYABHATA's changes"
                ),
                "metadata": {
                    "session_id": state.get("session_id", ""),
                    "scope_lines": review_scope_lines,
                    "scope_reason": "touched_lines_with_neighbor_radius",
                    "review_type": review_type,
                },
            },
        )
    state["review_type"] = review_type
    state["review_scope_lines"] = review_scope_lines

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
            fallback_result = await skill.run_with_fallback(
                patch_content=patch_text,
                kernel_version=str(state.get("kernel_version", "6.8")),
            )
            if isinstance(fallback_result, dict) and fallback_result.get("status") == "NEEDS_SOURCE":
                patchwise_status = {
                    "used": True,
                    "success": False,
                    "error": fallback_result.get("message"),
                    "fallback": True,
                    "missing_files": fallback_result.get("missing_files", []),
                }
                _emit(
                    state,
                    {
                        "agent": "chanakya",
                        "type": "warning",
                        "round": round_id,
                        "content": fallback_result.get("message", "PatchWise source files missing."),
                        "metadata": {
                            "missing_files": fallback_result.get("missing_files", []),
                            "patchwise_fallback": True,
                        },
                    },
                )
                patchwise_result = None
            else:
                patchwise_result = fallback_result
                patchwise_status = {
                    "used": True,
                    "success": bool(getattr(patchwise_result, "success", False)),
                    "error": getattr(patchwise_result, "error", None),
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
            "id": issue_id,
            "category": category,
            "type": category,
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
            "confidence": 0.85,
            "checkpatch_raw": raw_issue.get("description", ""),
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

    structured_issues = [
        issue
        for issue in structured_issues
        if not (
            issue.get("type") in {"STYLE", "LOGIC", "MEMORY", "COMPLIANCE"}
            and str(issue.get("problematic_code", "")).startswith("-")
        )
    ]

    if review_type == "SURGICAL" and review_scope_lines:
        scope_set = set(review_scope_lines)
        structured_issues = [
            item
            for item in structured_issues
            if int(item.get("line_number", 0) or 0) in scope_set
        ]

    prev_issues = state.get("previous_round_issues")
    if not isinstance(prev_issues, list):
        prev_issues = []
    fix_history = state.get("fix_history", [])
    prev_fix = fix_history[-1] if fix_history else None

    for issue in structured_issues:
        matching_prev = find_matching_issue(issue, prev_issues)
        if not matching_prev:
            continue

        issue["is_recurring"] = True
        issue["previous_round"] = matching_prev.get("first_seen_round", round_id - 1)
        issue["recurring_from_round"] = issue["previous_round"]
        issue["first_seen_round"] = issue["previous_round"]

        attempted = check_fix_attempted(issue, prev_fix.get("changes_made", []) if isinstance(prev_fix, dict) else [])
        if attempted:
            issue["fix_attempted"] = True
            issue["fix_failed_reason"] = detect_fix_failure_reason(issue, prev_fix)
        else:
            issue["missed_fix"] = True

        if issue["severity"] == "INFO":
            issue["severity"] = "WARNING"

    negotiation_state = state.get("negotiation_state", {}) if isinstance(state.get("negotiation_state"), dict) else {}
    for candidate in structured_issues:
        issue_id = candidate.get("issue_id")
        is_deadlock = await check_for_deadlock(
            issue_id=issue_id,
            session_id=state.get("session_id", ""),
            negotiation_state=negotiation_state,
        )
        if not is_deadlock:
            continue
        _emit(
            state,
            {
                "agent": "system",
                "type": "arbitration_required",
                "round": round_id,
                "content": f"Deadlock on Issue #{issue_id}; user arbitration required.",
                "metadata": {
                    "session_id": state.get("session_id", ""),
                    "issue_id": issue_id,
                    "chanakya_position": candidate.get("error_message", ""),
                    "aryabhata_position": candidate.get("suggested_fix", ""),
                    "evidence_summary": {
                        "recurring_from_round": candidate.get("recurring_from_round"),
                        "fix_failed_reason": candidate.get("fix_failed_reason"),
                        "reference": candidate.get("reference"),
                    },
                },
            },
        )
        shared = state.get("shared_a2a_context")
        if isinstance(shared, dict):
            shared["user_arbitration_pending"] = True
        break

    state["previous_round_issues"] = [dict(item) for item in structured_issues]

    structured_issues, analysis_mode = _enrich_issues_with_remote_llm(
        state=state,
        structured_issues=structured_issues,
        pw_result=patchwise_result,
    )

    for issue in structured_issues:
        _emit(
            state,
            {
                "agent": "chanakya",
                "type": "finding",
                "round": round_id,
                "content": issue["error_message"],
                "metadata": {
                    "issue_type": issue["type"],
                    "severity": issue["severity"],
                    "line_number": issue["line_number"],
                    "issue_id": issue["issue_id"],
                    "recurring": issue["is_recurring"],
                    "recurring_from_round": issue.get("recurring_from_round"),
                    "first_seen": issue["first_seen_round"],
                    "missed_fix": issue.get("missed_fix", False),
                    "fix_attempted": issue.get("fix_attempted", False),
                    "fix_failed_reason": issue.get("fix_failed_reason"),
                    "analysis_mode": analysis_mode,
                    "patchwise": patchwise_status,
                    "review_type": review_type,
                    "scope_lines": review_scope_lines if review_type == "SURGICAL" else None,
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

    critical_issues = [issue for issue in structured_issues if issue.get("severity") == "CRITICAL"]
    issue_count = len(structured_issues)
    quality_score = max(0.0, 100.0 - float(issue_count * 14))
    verdict = "LGTM" if not structured_issues else "NEEDS_WORK"

    if structured_issues and not critical_issues and round_id >= 2:
        _emit(
            state,
            {
                "agent": "chanakya",
                "type": "minor_issues_only",
                "round": round_id,
                "content": "Only non-critical issues remain.",
                "metadata": {"issue_count": issue_count},
            },
        )

    round_payload = {
        "round": round_id,
        "issues": structured_issues,
        "findings": structured_issues,
        "round_summary": f"Found {issue_count} issues — {len(critical_issues)} CRITICAL",
        "summary": f"Found {issue_count} issue(s).",
        "quality_score": quality_score,
        "analysis_mode": analysis_mode,
        "patchwise": patchwise_status,
        "lgtm": verdict == "LGTM",
        "surgical_focus": review_scope_lines if review_type == "SURGICAL" else [],
        "review_type": review_type,
    }

    _emit(
        state,
        {
            "agent": "system",
            "type": "a2a_message",
            "round": round_id,
            "content": f"CHANAKYA sent review report with {issue_count} issue(s).",
            "metadata": {
                "sender": "CHANAKYA",
                "receiver": "ARYABHATA",
                "type": "REVIEW_REPORT",
                "content": f"Round {round_id} review report",
                "issue_id": None,
                "round": round_id,
                "confidence": None,
                "message_id": f"rvw-{round_id:03d}",
                "timestamp": "",
                "metadata": {
                    "issue_count": issue_count,
                    "review_type": review_type,
                    "scope_lines": review_scope_lines if review_type == "SURGICAL" else [],
                },
            },
        },
    )

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

    state["quality_score"] = quality_score
    state["verdict"] = verdict
    shared = state.get("shared_a2a_context")
    if isinstance(shared, dict):
        shared.setdefault("chanakya_knowledge", {})
        shared["lgtm"] = verdict == "LGTM"
        shared["round_number"] = round_id
        shared["current_patch"] = state.get("current_patch", patch_text)
        shared["chanakya_knowledge"]["last_review_type"] = review_type
        shared["chanakya_knowledge"]["last_scope"] = (
            review_scope_lines if review_type == "SURGICAL" else "full"
        )
        state["shared_a2a_context"] = shared

    final_type = "lgtm" if verdict == "LGTM" else "verdict"
    _emit(
        state,
        {
            "agent": "chanakya",
            "type": final_type,
            "round": round_id,
            "content": "LGTM" if verdict == "LGTM" else "Needs work",
            "metadata": {
                "quality_score": quality_score,
                "issue_count": issue_count,
                "analysis_mode": analysis_mode,
                "patchwise": patchwise_status,
                "review_type": review_type,
                "scope_lines": review_scope_lines if review_type == "SURGICAL" else None,
            },
        },
    )

    state["interrupt_hint"] = None
    return state
