from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from knowledge.profile_manager import KnowledgeProfileManager

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])
manager = KnowledgeProfileManager()
SQLITE_PATH = os.getenv("SQLITE_PATH") or os.getenv("SQLITE_DB_PATH") or "/workspace/data/db/patchwise.db"


@router.post("/export")
async def export_profile(config: dict[str, Any]) -> FileResponse:
    pkb_path = await manager.export_profile(
        export_config=config,
        password=config.get("password"),
    )
    return FileResponse(
        pkb_path,
        media_type="application/octet-stream",
        filename=os.path.basename(pkb_path),
    )


@router.post("/import")
async def import_profile(file: UploadFile = File(...), password: Optional[str] = Form(None)) -> dict[str, Any]:
    suffix = Path(file.filename or "profile.pkb").suffix or ".pkb"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        results = await manager.import_profile(tmp_path, password)
        return {"success": True, "import_summary": results}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@router.get("/profile/summary")
async def get_profile_summary() -> dict[str, int]:
    conn = sqlite3.connect(SQLITE_PATH)
    try:
        summary = {
            "subsystem_rules": _safe_count(conn, "subsystem_rules"),
            "fix_patterns": _safe_query_count(conn, "SELECT COUNT(*) FROM fix_patterns WHERE success_count > 0"),
            "maintainer_prefs": _safe_count(conn, "maintainer_preferences"),
            "cover_letter_templates": _safe_count(conn, "cover_letter_templates"),
            "lkml_cache": _safe_count(conn, "lkml_cache"),
        }
        return summary
    finally:
        conn.close()


def _safe_count(conn: sqlite3.Connection, table: str) -> int:
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except Exception:
        return 0


def _safe_query_count(conn: sqlite3.Connection, query: str) -> int:
    try:
        return conn.execute(query).fetchone()[0]
    except Exception:
        return 0
