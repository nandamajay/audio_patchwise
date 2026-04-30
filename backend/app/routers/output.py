from fastapi import APIRouter, HTTPException

from app.runtime import REPORT_STORE, SESSION_STORE

router = APIRouter(prefix="/output", tags=["output"])


@router.get("/{session_id}/report")
def get_report(session_id: str) -> dict:
    if session_id not in SESSION_STORE:
        raise HTTPException(status_code=404, detail="session not found")
    report = REPORT_STORE.get(session_id)
    if report is None:
        return {
            "session_id": session_id,
            "status": "pending",
            "summary": "No report generated yet.",
        }
    return report


@router.get("/{session_id}/patch")
def get_patch_output(session_id: str) -> dict:
    state = SESSION_STORE.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="session not found")
    return {
        "session_id": session_id,
        "current_patch": state.get("current_patch", ""),
        "verdict": state.get("verdict", "PENDING"),
    }


@router.get("/{session_id}/log")
def get_log(session_id: str) -> dict:
    state = SESSION_STORE.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="session not found")
    return {
        "session_id": session_id,
        "conversation_log": state.get("conversation_log", []),
    }
