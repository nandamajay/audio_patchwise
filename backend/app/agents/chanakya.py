from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agents.chanakya_agent import CHANAKYA_ISSUE_FORMAT_PROMPT
from app.agents.state import PatchWiseState
from app.skills.patchwise_skill import full_patch_analysis
from app.skills.search_skill import SearchSkill


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
    suggestion = (issue.get("suggestion") or "").strip()
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


def chanakya_review_node(state: PatchWiseState) -> PatchWiseState:
    round_id = state.get("current_round", 1)
    patch_text = state.get("current_patch") or state.get("patch_input", "")
    source_context = state.get("source_path", "")
    session_id = state.get("session_id", "default")
    patch_lines = patch_text.splitlines()

    tracker = _ISSUE_TRACKERS.setdefault(session_id, IssueTracker())

    hint = state.get("interrupt_hint")
    thinking = "Analyzing style, logic, memory safety, compliance, and commit quality."
    if hint:
        thinking += f" Interrupt hint received: {hint}."
    _emit_tokens(state, "chanakya", "thinking", round_id, thinking)

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
            "metadata": {"quality_score": quality_score, "issue_count": issue_count},
        },
    )

    state["interrupt_hint"] = None
    return state
