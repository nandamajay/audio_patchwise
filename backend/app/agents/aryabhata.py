from __future__ import annotations

import json
import re
from typing import Any

from agents.aryabhata.fix_engine import AryabhataFixEngine
from agents.aryabhata.prompts import ARYABHATA_FIX_INSTRUCTION, ARYABHATA_SYSTEM_PROMPT
from core.llm_factory import get_llm

MARKER_START = "<<<FIXED_PATCH_START>>>"
MARKER_END = "<<<FIXED_PATCH_END>>>"


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


def _extract_blocks(text: str) -> list[str]:
    return [blk.strip() for blk in re.findall(rf"{re.escape(MARKER_START)}(.*?){re.escape(MARKER_END)}", text, re.DOTALL)]


def _issue_to_fix_payload(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw.get("issue_id") or raw.get("id") or "?",
        "type": raw.get("type") or raw.get("category") or raw.get("issue_type") or "STYLE",
        "description": raw.get("error_message") or raw.get("description") or raw.get("explanation") or "",
        "problematic_code": raw.get("problematic_code") or "",
        "suggested_fix": raw.get("suggested_fix") or raw.get("suggestion") or "",
        "line_number": int(raw.get("line_number", 0) or 0),
        "filename": raw.get("file_path") or raw.get("filename") or "",
        "category": raw.get("category") or raw.get("type") or "",
    }


def _line_numbers_from_diff(before: str, after: str) -> list[int]:
    if before == after:
        return []
    changed: list[int] = []
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    max_len = max(len(before_lines), len(after_lines))
    for idx in range(max_len):
        left = before_lines[idx] if idx < len(before_lines) else ""
        right = after_lines[idx] if idx < len(after_lines) else ""
        if left != right:
            changed.append(idx + 1)
    return sorted(set(changed))


def _chain_value(chain: Any, key: str, default: Any = None) -> Any:
    if isinstance(chain, dict):
        return chain.get(key, default)
    return getattr(chain, key, default)


def aryabhata_fix_node(state: dict[str, Any]) -> dict[str, Any]:
    round_id = int(state.get("current_round", 1) or 1)
    patch_content = state.get("current_patch") or state.get("patch_input", "")
    latest_review = state.get("latest_review", {})
    raw_issues = latest_review.get("issues") or latest_review.get("findings") or []
    if not raw_issues:
        review_history = state.get("review_findings", [])
        if isinstance(review_history, list) and review_history:
            latest = review_history[-1] if isinstance(review_history[-1], dict) else {}
            raw_issues = latest.get("issues") or latest.get("findings") or []
    issues = [_issue_to_fix_payload(item) for item in raw_issues if isinstance(item, dict)]

    if not issues:
        state["verdict"] = "LGTM"
        return state

    session_id = state.get("session_id", "")
    _emit(
        state,
        {
            "agent": "aryabhata",
            "type": "thinking",
            "round": round_id,
            "content": f"Applying concrete fixes for {len(issues)} CHANAKYA issues.",
            "metadata": {},
        },
    )

    deterministic: list[dict[str, Any]] = []
    cover_issues: list[dict[str, Any]] = []
    llm_issues: list[dict[str, Any]] = []
    for issue in issues:
        is_cover = (
            "cover" in issue.get("description", "").lower()
            or "cover-letter" in issue.get("filename", "").lower()
        )
        has_code = bool(issue.get("problematic_code", "").strip())
        has_fix = bool(issue.get("suggested_fix", "").strip())
        if is_cover:
            cover_issues.append(issue)
        elif not (has_code and has_fix):
            llm_issues.append(issue)
        else:
            deterministic.append(issue)

    engine = AryabhataFixEngine(
        subsystem=str(state.get("subsystem", "ASoC") or "ASoC"),
        kernel_version=str(state.get("kernel_version", "6.8") or "6.8"),
    )

    engine_result = engine.apply_all_fixes(
        patch_content=patch_content,
        issues=deterministic + cover_issues,
    )
    fixed_patch = engine_result.fixed_patch_content or patch_content
    cover_letter = engine_result.cover_letter_content
    changed_lines = list(engine_result.changed_lines)

    if llm_issues:
        llm_provider = state.get("llm_provider")
        llm_model = state.get("llm_model")
        try:
            llm = get_llm(model=llm_model, provider=llm_provider, temperature=0.2, streaming=True)
            prompt = ARYABHATA_FIX_INSTRUCTION.format(
                issues_json=json.dumps(llm_issues, indent=2),
                patch_content=fixed_patch[:8000],
                kernel_version=state.get("kernel_version", "6.8"),
                subsystem=state.get("subsystem", "ASoC"),
                patch_version=_chain_value(state.get("version_chain"), "current_version", ""),
                prev_version_links=json.dumps(_chain_value(state.get("version_chain"), "previous_links", [])),
            )
            response = llm.invoke(f"{ARYABHATA_SYSTEM_PROMPT}\n\n{prompt}")
            text = getattr(response, "content", response)
            if isinstance(text, list):
                text = "\n".join(str(item) for item in text)
            text = str(text or "")
            blocks = _extract_blocks(text)
            if blocks:
                for blk in blocks:
                    lowered = blk.lower()
                    if "0/" in blk or "cover-letter" in lowered:
                        cover_letter = blk
                    else:
                        old = fixed_patch
                        fixed_patch = blk
                        changed_lines.extend(_line_numbers_from_diff(old, fixed_patch))
            else:
                _emit(
                    state,
                    {
                        "agent": "aryabhata",
                        "type": "warning",
                        "round": round_id,
                        "content": "LLM did not provide FIXED_PATCH markers; using deterministic fix output.",
                        "metadata": {},
                    },
                )
        except Exception as exc:
            _emit(
                state,
                {
                    "agent": "aryabhata",
                    "type": "warning",
                    "round": round_id,
                    "content": f"LLM-assisted fix path unavailable ({exc}); used deterministic fixes.",
                    "metadata": {},
                },
            )

    changed_lines = sorted(set(line for line in changed_lines if line > 0))

    fix_summary = []
    for issue in issues:
        fix_summary.append(
            {
                "issue_id": issue.get("id", "?"),
                "category": issue.get("type", "STYLE"),
                "line": issue.get("line_number", 0),
                "problem": issue.get("description", ""),
                "fix": issue.get("suggested_fix", ""),
                "status": "FIXED",
            }
        )

    marked_patch = f"{MARKER_START}\n{fixed_patch}\n{MARKER_END}"
    justification = engine_result.justification or "Applied line-level fixes and produced updated patch content."
    _emit(
        state,
        {
            "agent": "aryabhata",
            "type": "fix_complete",
            "round": round_id,
            "content": f"Applied {len(fix_summary)} fixes to patch content.",
            "fix_summary": fix_summary,
            "changes_made": [
                {
                    "issue_id": item.get("id"),
                    "issue_type": item.get("type"),
                    "line": item.get("line_number"),
                    "original": item.get("problematic_code"),
                    "fixed": item.get("suggested_fix"),
                    "reason": item.get("description"),
                }
                for item in issues
            ],
            "diff_from_previous": "",
            "fixed_patch": fixed_patch,
            "cover_letter": cover_letter,
            "cover_letter_filename": "0000-cover-letter.patch" if cover_letter else None,
            "original_patch": patch_content,
            "checkpatch_output": "",
            "validation_passed": engine_result.success,
            "justification": justification,
            "changed_lines": changed_lines,
            "surgical_review_request": {
                "lines": changed_lines,
                "message": f"CHANAKYA: please re-check lines {changed_lines} only",
            },
            "patch_marker_start": MARKER_START,
            "patch_marker_end": MARKER_END,
            "marked_patch": marked_patch,
        },
    )

    _ensure_list(state, "fix_history").append(
        {
            "round": round_id,
            "fixes_applied": len(fix_summary),
            "changes_made": [
                {
                    "issue_id": item.get("id"),
                    "issue_type": item.get("type"),
                    "line": item.get("line_number"),
                }
                for item in issues
            ],
            "validation_passed": engine_result.success,
        }
    )
    _ensure_list(state, "fix_attempts").append(
        {
            "round": round_id,
            "fixes": fix_summary,
            "summary": f"Applied {len(fix_summary)} fix(es).",
            "fixed_patch": fixed_patch,
            "cover_letter": cover_letter,
            "cover_letter_filename": "0000-cover-letter.patch" if cover_letter else None,
            "validation_passed": engine_result.success,
            "patch_marker_start": MARKER_START,
            "patch_marker_end": MARKER_END,
            "changed_lines": changed_lines,
        }
    )
    _ensure_list(state, "conversation_log").append(
        {
            "round": round_id,
            "agent": "aryabhata",
            "message": f"Applied {len(fix_summary)} fixes.",
            "changed_lines": changed_lines,
        }
    )

    state["current_patch"] = fixed_patch
    state["cover_letter_content"] = cover_letter
    state["aryabhata_fix_complete"] = True
    state["aryabhata_changed_lines"] = changed_lines
    state["touched_lines"] = changed_lines
    state["surgical_review_lines"] = changed_lines
    state["current_round"] = round_id + 1
    state["verdict"] = "PENDING"
    state["interrupt_hint"] = None

    shared = state.get("shared_a2a_context")
    if isinstance(shared, dict):
        shared["touched_lines"] = changed_lines
        shared["current_patch"] = fixed_patch
        shared["aryabhata_fix_result"] = {
            "success": engine_result.success,
            "errors": engine_result.errors,
            "changed_lines": changed_lines,
            "justification": justification,
        }

    if session_id:
        _emit(
            state,
            {
                "agent": "system",
                "type": "a2a_message",
                "round": round_id,
                "content": "ARYABHATA produced fixed patch content.",
                "metadata": {
                    "sender": "ARYABHATA",
                    "receiver": "CHANAKYA",
                    "type": "FIX_PROPOSAL",
                    "issue_id": None,
                    "round": round_id,
                    "message_id": f"fix-{round_id:03d}",
                    "timestamp": "",
                    "metadata": {
                        "changed_lines": changed_lines,
                        "cover_letter_generated": bool(cover_letter),
                    },
                },
            },
        )

    return state
