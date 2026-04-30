from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.dependencies import engine, session_manager
from submission.submission_engine import SubmissionTarget

router = APIRouter(prefix="/api/submit", tags=["submission"])


class SubmissionRequest(BaseModel):
    session_id: str
    target: SubmissionTarget
    target_repo: Optional[str] = None
    base_branch: Optional[str] = "main"
    gerrit_url: Optional[str] = None
    checklist_confirmed: bool = False


@router.post("/")
async def submit_patch(req: SubmissionRequest):
    if not req.checklist_confirmed:
        raise HTTPException(
            status_code=400,
            detail="Approval checklist must be confirmed before submission",
        )

    payload = req.model_dump()
    if req.target == SubmissionTarget.GITHUB:
        result = await engine.submit_to_github(req.session_id, payload)
    elif req.target == SubmissionTarget.GERRIT:
        result = await engine.submit_to_gerrit(req.session_id, payload)
    elif req.target == SubmissionTarget.UPSTREAM:
        result = await engine.format_upstream_patch(req.session_id)
    else:
        result = await engine.download_patch(req.session_id)

    session_manager.update_session(
        req.session_id,
        status="submitted",
        submission=result,
    )

    return result


@router.get("/checklist/{session_id}")
async def get_checklist(session_id: str):
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    report = session.review_report or {}
    issues = session.issues_found or []

    return {
        "items": [
            {
                "id": "verdict_lgtm",
                "label": "CHANAKYA has given LGTM verdict",
                "checked": session.verdict == "LGTM",
            },
            {
                "id": "checkpatch_pass",
                "label": "checkpatch.pl passes with no errors",
                "checked": bool(report.get("checkpatch_passed", False)),
            },
            {
                "id": "issues_resolved",
                "label": "All critical issues resolved",
                "checked": all(
                    item.get("resolved", False)
                    for item in issues
                    if isinstance(item, dict) and item.get("severity") == "critical"
                ),
            },
            {
                "id": "diff_reviewed",
                "label": "Diff manually reviewed by user",
                "checked": False,
            },
            {
                "id": "target_selected",
                "label": "Submission target selected",
                "checked": False,
            },
        ]
    }
