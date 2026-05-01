from fastapi import APIRouter, HTTPException

from app.runtime import REPORT_STORE, SESSION_STORE

try:
    from api.dependencies import session_manager
except Exception:  # pragma: no cover
    session_manager = None

router = APIRouter(prefix="/output", tags=["output"])


def _get_session_snapshot(session_id: str):
    if not session_manager:
        return None
    return session_manager.get_session(session_id)


@router.get("/{session_id}/report")
def get_report(session_id: str) -> dict:
    runtime_state = SESSION_STORE.get(session_id)
    snapshot = _get_session_snapshot(session_id)
    if runtime_state is None and snapshot is None:
        raise HTTPException(status_code=404, detail="session not found")

    report = REPORT_STORE.get(session_id)
    if report is None and snapshot and snapshot.review_report:
        return snapshot.review_report

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
    snapshot = _get_session_snapshot(session_id)
    if state is None and snapshot is None:
        raise HTTPException(status_code=404, detail="session not found")

    if state is None and snapshot is not None:
        patch_text = snapshot.final_patch or (snapshot.patch_input or {}).get("raw_text", "")
        return {
            "session_id": session_id,
            "current_patch": patch_text,
            "verdict": snapshot.verdict or "PENDING",
        }

    return {
        "session_id": session_id,
        "current_patch": state.get("current_patch", ""),
        "verdict": state.get("verdict", "PENDING"),
    }


@router.get("/{session_id}/log")
def get_log(session_id: str) -> dict:
    state = SESSION_STORE.get(session_id)
    snapshot = _get_session_snapshot(session_id)
    if state is None and snapshot is None:
        raise HTTPException(status_code=404, detail="session not found")

    if state is None and snapshot is not None:
        return {
            "session_id": session_id,
            "conversation_log": snapshot.conversation or [],
        }

    return {
        "session_id": session_id,
        "conversation_log": state.get("conversation_log", []),
    }
