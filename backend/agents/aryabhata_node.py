from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from agents.aryabhata_fix_engine import AryabhataFixEngine
from core.llm_factory import get_llm


ARYABHATA_SYSTEM_PROMPT = """
You are ARYABHATA — the Developer Agent in the PatchWise A2A system.
You receive CHANAKYA's review findings and produce REAL patch fixes.

ABSOLUTE RULES — NEVER VIOLATE:

RULE 1 — YOU MUST OUTPUT REAL PATCH CONTENT:
After analyzing issues you MUST output the fixed patch between these exact markers:
<<<FIXED_PATCH_START>>>
[complete modified .patch file content here]
<<<FIXED_PATCH_END>>>

RULE 2 — NEVER SAY "I WILL FIX" WITHOUT THE ACTUAL FIX:
"Show Justification" alone is NOT acceptable.
Every response MUST contain <<<FIXED_PATCH_START>>> markers with real content.

RULE 3 — FIX ALL ACCEPTED ISSUES IN ONE PASS:
Do not fix one issue at a time. Apply ALL accepted fixes in one response.
If you challenge an issue, still fix all non-challenged issues.

RULE 4 — COMMIT MESSAGE FIXES ARE MANDATORY:
If CHANAKYA flags Subject prefix — you MUST fix it in the patch header.
If CHANAKYA flags Signed-off-by — you MUST add it.
These are not optional.

RULE 5 — SHOW INLINE DIFF FOR EACH FIX:
For each fix, show:
- LINE NUMBER: [n]
- BEFORE: [exact original line]
- AFTER: [exact fixed line]
- WHY: [one line justification]

RULE 6 — CHALLENGE PROTOCOL:
You MAY challenge ONE issue per review if you have strong evidence.
Format: CHALLENGE: Issue #[n] — [your evidence from kernel docs/LKML]
But STILL fix all other non-challenged issues in the SAME response.
"""


@dataclass
class AgentMessage:
    sender: str
    receiver: str
    message_type: str
    content: str
    metadata: Dict[str, Any]


def _extract_issues(state: Any) -> List[dict]:
    report = getattr(state, "current_review_report", None) if not isinstance(state, dict) else state.get("current_review_report")
    if report is None:
        return []
    if isinstance(report, dict):
        issues = report.get("issues") or report.get("findings") or []
        return issues if isinstance(issues, list) else []
    issues = getattr(report, "issues", [])
    return issues if isinstance(issues, list) else []


def _get_value(state: Any, key: str, default: Any = None) -> Any:
    if isinstance(state, dict):
        return state.get(key, default)
    return getattr(state, key, default)


def _set_value(state: Any, key: str, value: Any) -> None:
    if isinstance(state, dict):
        state[key] = value
    else:
        setattr(state, key, value)


def get_llm_client(llm_config: Any):
    provider = _get_value(llm_config, "provider", None)
    model = _get_value(llm_config, "model", None)
    return get_llm(model=model, provider=provider, temperature=0.2, streaming=True)


def format_issues_for_aryabhata(issues: List[dict]) -> str:
    return json.dumps(issues, indent=2, ensure_ascii=False)


def format_shared_context(ctx: Any) -> str:
    if not ctx:
        return "{}"
    if isinstance(ctx, dict):
        return json.dumps(ctx, indent=2, ensure_ascii=False, default=str)
    try:
        return json.dumps(ctx.__dict__, indent=2, ensure_ascii=False, default=str)
    except Exception:
        return str(ctx)


def format_round_history(history: Any) -> str:
    if not history:
        return "[]"
    try:
        return json.dumps(history, indent=2, ensure_ascii=False, default=str)
    except Exception:
        return str(history)


def extract_fixed_patch(response_text: str) -> Optional[str]:
    start_marker = "<<<FIXED_PATCH_START>>>"
    end_marker = "<<<FIXED_PATCH_END>>>"
    start_idx = response_text.find(start_marker)
    end_idx = response_text.find(end_marker)
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        return response_text[start_idx + len(start_marker) : end_idx].strip()
    return None


def extract_challenges(response_text: str) -> List[str]:
    return re.findall(r"CHALLENGE:\s*(.*)", response_text)


def extract_touched_lines(fix_result: Any) -> List[int]:
    touched: List[int] = []
    for change in getattr(fix_result, "changes_made", []) or []:
        try:
            touched.append(int(change.get("line", 0)))
        except Exception:
            continue
    return sorted({line for line in touched if line > 0})


async def force_fix_via_engine(
    engine: AryabhataFixEngine,
    patch_content: str,
    issues: List[dict],
    state: Any,
) -> str:
    author = _get_value(_get_value(state, "config", {}), "author", "Developer <dev@example.com>")
    result = await engine.apply_fixes(patch_content, issues, author=author)
    return result.fixed_patch_content


async def aryabhata_node(state: Any) -> Any:
    """
    ARYABHATA node — produces REAL patch fixes with marker enforcement.
    """
    fix_engine = AryabhataFixEngine()

    llm_config = _get_value(state, "llm_config", {})
    llm = get_llm_client(llm_config)

    current_round = int(_get_value(state, "current_round", 1) or 1)
    original_patch = _get_value(state, "original_patch", "")
    current_patch = _get_value(state, "current_fixed_patch", None) or original_patch
    chanakya_issues = _extract_issues(state)

    messages = [
        {"role": "system", "content": ARYABHATA_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"""
CHANAKYA REVIEW REPORT — Round {current_round}:
{format_issues_for_aryabhata(chanakya_issues)}

ORIGINAL PATCH:
{original_patch}

SHARED CONTEXT:
{format_shared_context(_get_value(state, 'shared_a2a_context', {}))}

PREVIOUS ROUNDS HISTORY:
{format_round_history(_get_value(state, 'round_history', []))}

INSTRUCTIONS:
1. For each issue — decide: ACCEPT or CHALLENGE (max 1 challenge)
2. Apply ALL accepted fixes to the patch
3. Output complete fixed patch between markers
4. Show inline diff for each fix
""",
        },
    ]

    response_text = ""
    try:
        for msg in messages:
            # keep prompt in one invoke for wider model compatibility
            pass
        llm_response = llm.invoke("\n\n".join([m["content"] for m in messages]))
        response_text = getattr(llm_response, "content", str(llm_response)) or ""
        if isinstance(response_text, list):
            response_text = "\n".join([str(item) for item in response_text])
    except Exception as exc:
        response_text = f"LLM generation failed: {exc}"

    fixed_patch = extract_fixed_patch(response_text)
    if not fixed_patch:
        fixed_patch = await force_fix_via_engine(fix_engine, current_patch, chanakya_issues, state)
        response_text += "\n[ARYABHATA FIX ENGINE APPLIED — real patch generated]"

    author = _get_value(_get_value(state, "config", {}), "author", "Developer <dev@example.com>")
    fix_result = await fix_engine.apply_fixes(fixed_patch, chanakya_issues, author=author)

    shared = _get_value(state, "shared_a2a_context", {}) or {}
    if isinstance(shared, dict):
        shared["aryabhata_fix_result"] = fix_result
        shared["touched_lines"] = extract_touched_lines(fix_result)
        _set_value(state, "shared_a2a_context", shared)

    _set_value(state, "current_fixed_patch", fix_result.fixed_patch_content)

    message = AgentMessage(
        sender="ARYABHATA",
        receiver="CHANAKYA",
        message_type="FIX_PROPOSAL",
        content=response_text,
        metadata={
            "changes_made": fix_result.changes_made,
            "touched_lines": extract_touched_lines(fix_result),
            "validation_passed": fix_result.validation_passed,
            "checkpatch_output": fix_result.checkpatch_output,
            "challenges": extract_challenges(response_text),
            "fixed_patch_preview": fix_result.fixed_patch_content[:500],
            "patch_marker_start": "<<<FIXED_PATCH_START>>>",
            "patch_marker_end": "<<<FIXED_PATCH_END>>>",
        },
    )

    msgs = _get_value(state, "a2a_messages", []) or []
    msgs.append(message)
    _set_value(state, "a2a_messages", msgs)
    return state
