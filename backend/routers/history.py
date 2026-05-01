from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from services.history_manager import history_manager

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("/sessions")
def list_sessions(
    search: Optional[str] = Query(default=None),
    subsystem: Optional[str] = Query(default=None),
    verdict: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0),
):
    filters: dict[str, str] = {}
    if subsystem:
        filters["subsystem"] = subsystem
    if verdict:
        filters["verdict"] = verdict
    if date_from:
        filters["date_from"] = date_from
    if date_to:
        filters["date_to"] = date_to
    return history_manager.list_sessions(filters=filters, search=search, limit=limit, offset=offset)


@router.get("/sessions/{session_id}")
def get_session(session_id: str):
    session = history_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/sessions/{session_id}/rounds")
def get_rounds(session_id: str):
    return history_manager.get_rounds(session_id)


@router.get("/sessions/{session_id}/messages")
def get_messages(session_id: str):
    return history_manager.get_messages(session_id)


@router.get("/sessions/{session_id}/analytics")
def get_analytics(session_id: str):
    session = history_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return history_manager.get_session_analytics(session_id)


@router.get("/sessions/{session_id}/replay")
def get_replay(session_id: str):
    session = history_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    rounds = history_manager.get_rounds(session_id)
    messages = history_manager.get_messages(session_id)
    with history_manager._conn() as conn:  # noqa: SLF001
        rows = conn.execute(
            "SELECT * FROM session_references WHERE session_id=?",
            (session_id,),
        ).fetchall()
        refs = [dict(row) for row in rows]
    return {"rounds": rounds, "messages": messages, "references": refs}


@router.get("/sessions/{session_id}/export/{export_type}")
def export_session(session_id: str, export_type: str):
    exporters = {
        "pdf": history_manager.export_pdf,
        "markdown": history_manager.export_markdown,
        "patch": history_manager.export_patch,
        "zip": history_manager.export_zip,
    }
    if export_type not in exporters:
        raise HTTPException(status_code=400, detail="Invalid export type")

    session = history_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    path = exporters[export_type](session_id)
    filename = path.split("/")[-1]
    return FileResponse(path, filename=filename)


@router.get("/stats")
def global_stats():
    return history_manager.get_global_stats()


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    with history_manager._conn() as conn:  # noqa: SLF001
        conn.execute("DELETE FROM patch_sessions WHERE id=?", (session_id,))
        conn.execute("DELETE FROM session_rounds WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM session_messages WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM session_references WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM session_exports WHERE session_id=?", (session_id,))

    return {"status": "deleted"}
