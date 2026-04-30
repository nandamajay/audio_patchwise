from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.runtime import SESSION_STORE

router = APIRouter(tags=["interrupt"])


class InterruptPayload(BaseModel):
    hint: str


@router.post("/session/{session_id}/interrupt")
def interrupt_session(session_id: str, payload: InterruptPayload) -> dict:
    state = SESSION_STORE.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="session not found")
    state["interrupt_hint"] = payload.hint
    return {"status": "accepted", "session_id": session_id, "hint": payload.hint}
