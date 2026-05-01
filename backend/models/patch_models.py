from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ReviewIssue(BaseModel):
    issue_id: str
    category: str  # STYLE | LOGIC | MEMORY | COMMIT | COMPLIANCE
    severity: str  # CRITICAL | WARNING | INFO
    line_number: int
    file_path: str
    hunk_context: str
    error_message: str
    problematic_code: str
    suggested_fix: str
    explanation: str
    reference: Optional[str] = None
    is_recurring: bool = False
    previous_round: Optional[int] = None
    round_number: Optional[int] = None
    context: Dict = Field(default_factory=dict)


class PatchHunk(BaseModel):
    header: str
    file_path: str = ""
    lines: List[str] = Field(default_factory=list)


class LineEdit(BaseModel):
    line_number: int
    original_line: str
    fixed_line: str
    issue_id: str
    category: str
    justification: str


class FixResult(BaseModel):
    fixed_patch: str
    applied_fixes: Dict[str, LineEdit]
    validation_result: Dict
    diff_from_previous: str
    issues_addressed: List[str]
    checkpatch_output: str


class AryabhataFixMessage(BaseModel):
    agent: str = "ARYABHATA"
    type: str = "fix_complete"
    fix_summary: List[Dict]
    diff_from_previous: str
    fixed_patch: str
    validation_passed: bool
    checkpatch_output: str
    justification: Optional[str] = None
