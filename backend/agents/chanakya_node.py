from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


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
"""


@dataclass
class ChanakyaReviewReport:
    issues: list[dict[str, Any]] = field(default_factory=list)
    round_summary: str = ""
    lgtm: bool = False
    surgical_focus: list[int] = field(default_factory=list)
    raw_output: str = ""


def _extract_json_payload(text: str) -> dict[str, Any] | None:
    if not text:
        return None

    candidates = [text]
    first = min([idx for idx in [text.find("{"), text.find("[")] if idx >= 0], default=-1)
    if first >= 0:
        candidates.append(text[first:])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list):
            return {"issues": parsed}
    return None


def parse_chanakya_output(response_text: str) -> ChanakyaReviewReport:
    payload = _extract_json_payload(response_text) or {}
    issues = payload.get("issues")
    if not isinstance(issues, list):
        issues = []

    normalized: list[dict[str, Any]] = []
    for idx, issue in enumerate(issues, start=1):
        if not isinstance(issue, dict):
            continue
        issue_id = str(issue.get("id") or issue.get("issue_id") or f"issue_{idx:03d}")
        issue_type = str(issue.get("type") or issue.get("category") or "STYLE").upper()
        normalized.append(
            {
                "id": issue_id,
                "issue_id": issue_id,
                "type": issue_type,
                "category": issue_type,
                "severity": str(issue.get("severity") or "WARNING").upper(),
                "line_number": int(issue.get("line_number") or 1),
                "file_path": str(issue.get("file_path") or "unknown"),
                "problematic_code": str(issue.get("problematic_code") or ""),
                "suggested_fix": str(issue.get("suggested_fix") or ""),
                "explanation": str(issue.get("explanation") or ""),
                "reference": issue.get("reference"),
                "confidence": float(issue.get("confidence") or 0.0),
                "checkpatch_raw": str(issue.get("checkpatch_raw") or ""),
            }
        )

    surgical_focus = payload.get("surgical_focus")
    if not isinstance(surgical_focus, list):
        surgical_focus = []
    focus_lines: list[int] = []
    for item in surgical_focus:
        try:
            focus_lines.append(int(item))
        except Exception:
            continue

    return ChanakyaReviewReport(
        issues=normalized,
        round_summary=str(payload.get("round_summary") or f"Found {len(normalized)} issues"),
        lgtm=bool(payload.get("lgtm", False)),
        surgical_focus=sorted(set(focus_lines)),
        raw_output=response_text,
    )
