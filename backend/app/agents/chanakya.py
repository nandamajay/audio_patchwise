from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from agents.chanakya_agent import CHANAKYA_ISSUE_FORMAT_PROMPT
from app.agents.state import PatchWiseState
from app.skills.patchwise_skill import full_patch_analysis
from app.skills.search_skill import SearchSkill
from core.llm_factory import get_llm
from core.patchwise_skill import PatchWiseResult, PatchWiseSkill


CHANAKYA_SYSTEM_PROMPT = (
    "You are CHANAKYA, a sharp analytical kernel patch reviewer. "
    "You must provide line-specific, structured, upstream-relevant issues.\n\n"
    + CHANAKYA_ISSUE_FORMAT_PROMPT
)


@dataclass
class IssueHistory:
    count: int
    first_round: int
    last_round: int
    issue_id: str


@dataclass
class IssueTracker:
    issue_history: dict[str, IssueHistory] = field(default_factory=dict)

    def _key(self, issue: dict[str, Any]) -> str:
        return f"{issue.get('category')}|{issue.get('line_number')}|{issue.get('error_message')[:80]}"

    def track(self, issue: dict[str, Any], round_num: int) -> tuple[bool, int | None]:
        key = self._key(issue)
        if key not in self.issue_history:
            self.issue_history[key] = IssueHistory(
                count=1,
                first_round=round_num,
                last_round=round_num,
                issue_id=issue["issue_id"],
            )
            return False, None
        history = self.issue_history[key]
        history.count += 1
        history.last_round = round_num
        return True, history.first_round


_ISSUE_TRACKERS: dict[str, IssueTracker] = {}
_PATCHWISE_SKILL: PatchWiseSkill | None = None
_PATCHWISE_INIT_ERROR: str | None = None


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


def _next_severity(severity: str) -> str:
    if severity == "INFO":
        return "WARNING"
    if severity == "WARNING":
        return "CRITICAL"
    return "CRITICAL"


def _default_fix(problematic: str, issue: dict[str, Any]) -> str:
    suggestion = (issue.get("suggestion") or issue.get("suggested_fix") or "").strip()
    issue_type = issue.get("issue_type", "")
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
    idxs = [i for i in (first_brace, first_bracket) if i >= 0]
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


def _build_review_prompt(
    patch_text: str,
    pw_result: PatchWiseResult,
    state: PatchWiseState,
) -> str:
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


def chanakya_review_node(state: PatchWiseState) -> PatchWiseState:
    round_id = state.get("current_round", 1)
    patch_text = state.get("current_patch") or state.get("patch_input", "")
    source_context = state.get("source_path", "")
    session_id = state.get("session_id", "default")
    patch_lines = patch_text.splitlines()

    tracker = _ISSUE_TRACKERS.setdefault(session_id, IssueTracker())

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
            patchwise_result = skill.review_patch_file(
                patch_content=patch_text,
                kernel_path=source_context or None,
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

    similar_refs = SearchSkill().search(
        patch_text,
        subsystem=state.get("subsystem", "alsa-asoc"),
        sources=["lkml", "gerrit", "local"],
    )

    structured_issues: list[dict[str, Any]] = []
    issue_counter = 1
    for bucket, items in analyses.items():
        category = _category(bucket)
        for raw_issue in items:
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
                "round_number": round_id,
            }

            recurring, first_round = tracker.track(issue, round_id)
            if recurring:
                issue["is_recurring"] = True
                issue["previous_round"] = first_round
                issue["severity"] = _next_severity(issue["severity"])
                issue["explanation"] = (
                    f"ARYABHATA failed to address this in Round {first_round}. "
                    f"The fix MUST modify line {line_number} to: {issue['suggested_fix']}. "
                    f"{issue['explanation']}"
                )

            issue["similar_patch_refs"] = similar_refs[:2]
            structured_issues.append(issue)

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
                    "issue_type": issue["category"],
                    "severity": issue["severity"],
                    "line_number": issue["line_number"],
                    "issue_id": issue["issue_id"],
                    "recurring": issue["is_recurring"],
                    "first_seen": issue["previous_round"],
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
                "content": ref["title"],
                "metadata": ref,
            },
        )

    issue_count = len(structured_issues)
    quality_score = max(0.0, 100.0 - float(issue_count * 14))
    verdict = "LGTM" if issue_count == 0 else "NEEDS_WORK"

    round_payload = {
        "round": round_id,
        "issues": structured_issues,
        "findings": structured_issues,
        "summary": f"Found {issue_count} issue(s).",
        "quality_score": quality_score,
        "analysis_mode": analysis_mode,
        "patchwise": patchwise_status,
    }
    state["latest_review"] = round_payload
    state.setdefault("review_findings", []).append(round_payload)
    state.setdefault("similar_patches", []).extend(similar_refs)
    state.setdefault("conversation_log", []).append(
        {
            "round": round_id,
            "agent": "chanakya",
            "message": f"Review complete. {issue_count} issue(s).",
            "findings": structured_issues,
        }
    )
    state["quality_score"] = quality_score
    state["verdict"] = verdict

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
            },
        },
    )

    state["interrupt_hint"] = None
    return state
