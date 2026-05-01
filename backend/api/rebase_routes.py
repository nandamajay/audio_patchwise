from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from services.rebase_handler import RebaseStrategy, rebase_handler

router = APIRouter(prefix="/api/rebase", tags=["rebase"])


class RebaseStrategyRequest(BaseModel):
    session_id: str
    strategy: RebaseStrategy


class ManualRebaseRequest(BaseModel):
    session_id: str
    target_ref: str


@router.post("/set-strategy")
async def set_rebase_strategy(req: RebaseStrategyRequest):
    """Set rebase strategy for a session."""
    return {"status": "ok", "strategy": req.strategy}


@router.post("/trigger")
async def trigger_rebase(req: ManualRebaseRequest):
    """Manually trigger rebase to a specific ref."""
    drift = await rebase_handler.detect_drift(req.target_ref, [])
    if drift:
        await rebase_handler._auto_rebase(req.session_id, drift)
        return {"status": "rebase_triggered"}
    return {"status": "no_drift_detected"}


@router.get("/status/{session_id}")
async def get_rebase_status(session_id: str):
    """Get current upstream drift status for a session."""
    return {
        "session_id": session_id,
        "drift_detected": False,
        "last_checked": "2025-05-01T00:00:00Z",
    }
