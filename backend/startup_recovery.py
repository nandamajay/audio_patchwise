"""
PatchWise startup recovery checks.

Runs on each backend start, validates persistent stores, and recovers any
in-flight sessions left in a running state after an unexpected stop.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("patchwise.startup")

SQLITE_PATH = os.getenv("SQLITE_PATH") or os.getenv("SQLITE_DB_PATH") or "/workspace/data/db/patchwise.db"
CHROMADB_PATH = os.getenv("CHROMADB_PATH", "/workspace/data/chromadb")
PROFILES_PATH = os.getenv("PROFILES_PATH", "/workspace/data/profiles")
BACKUPS_PATH = os.getenv("BACKUPS_PATH", "/workspace/data/backups")


def _connect_sqlite() -> sqlite3.Connection:
    Path(SQLITE_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row)


async def run_startup_recovery() -> dict[str, Any]:
    logger.info("PatchWise startup recovery: begin")
    results: dict[str, Any] = {}
    results["sqlite"] = await check_sqlite_integrity()
    results["chromadb"] = await check_chromadb_health()
    results["sessions"] = await recover_interrupted_sessions()
    results["lkml"] = await check_lkml_seed_status()
    results["profiles"] = await reload_agent_profiles()
    results["backups"] = await verify_latest_backup()
    logger.info("PatchWise startup recovery: complete %s", results)
    return results


async def check_sqlite_integrity() -> dict[str, Any]:
    try:
        conn = _connect_sqlite()
        result = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        if result and result[0] == "ok":
            return {"status": "ok", "mode": "WAL"}
        return {"status": "error", "detail": str(result)}
    except Exception as exc:
        logger.exception("Startup sqlite integrity failed")
        return {"status": "error", "detail": str(exc)}


async def check_chromadb_health() -> dict[str, Any]:
    try:
        import chromadb

        Path(CHROMADB_PATH).mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=CHROMADB_PATH)
        collections = client.list_collections()
        names = [c.name for c in collections]
        required = {"lkml_patches", "fix_patterns", "review_patterns", "maintainer_prefs"}
        missing = sorted(list(required - set(names)))
        for collection_name in missing:
            client.get_or_create_collection(name=collection_name)
        return {
            "status": "ok",
            "collections": sorted(set(names + missing)),
            "missing_created": missing,
        }
    except Exception as exc:
        logger.exception("Startup chromadb health failed")
        return {"status": "error", "detail": str(exc)}


async def recover_interrupted_sessions() -> dict[str, Any]:
    try:
        conn = _connect_sqlite()
        if not _table_exists(conn, "sessions"):
            conn.close()
            return {"status": "ok", "recovered_count": 0, "detail": "sessions table missing"}

        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()
        }
        session_col = "session_id" if "session_id" in columns else ("id" if "id" in columns else None)
        round_col = "current_round" if "current_round" in columns else (
            "rounds_completed" if "rounds_completed" in columns else None
        )
        if not session_col:
            conn.close()
            return {"status": "ok", "recovered_count": 0, "detail": "sessions table has no session key column"}

        select_cols = [session_col]
        if round_col:
            select_cols.append(round_col)
        rows = conn.execute(
            f"SELECT {', '.join(select_cols)} FROM sessions WHERE lower(status) IN ('running','in_progress')"
        ).fetchall()

        recovered: list[dict[str, Any]] = []
        interrupted_at = datetime.now(timezone.utc).isoformat()

        if _table_exists(conn, "sessions"):
            for row in rows:
                if "updated_at" in columns:
                    conn.execute(
                        f"UPDATE sessions SET status = ?, updated_at = ? WHERE {session_col} = ?",
                        ("interrupted", interrupted_at, row[session_col]),
                    )
                else:
                    conn.execute(
                        f"UPDATE sessions SET status = ? WHERE {session_col} = ?",
                        ("interrupted", row[session_col]),
                    )
                recovered.append(
                    {
                        "session_id": row[session_col],
                        "round": row[round_col] if round_col else None,
                    }
                )
        conn.commit()
        conn.close()
        return {"status": "ok", "recovered_count": len(recovered), "sessions": recovered}
    except Exception as exc:
        logger.exception("Startup interrupted-session recovery failed")
        return {"status": "error", "detail": str(exc)}


async def check_lkml_seed_status() -> dict[str, Any]:
    try:
        conn = _connect_sqlite()
        if not _table_exists(conn, "lkml_seed_status"):
            conn.close()
            return {"status": "needs_seed", "action": "schedule_initial_seed"}

        row = conn.execute(
            """
            SELECT last_seeded_at, patches_count
            FROM lkml_seed_status
            WHERE subsystem = 'alsa-asoc'
            ORDER BY last_seeded_at DESC
            LIMIT 1
            """
        ).fetchone()
        conn.close()
        if not row:
            return {"status": "needs_seed", "action": "schedule_initial_seed"}
        return {"status": "ok", "last_seeded": row["last_seeded_at"], "patches": row["patches_count"]}
    except Exception as exc:
        logger.exception("Startup lkml seed check failed")
        return {"status": "error", "detail": str(exc)}


async def reload_agent_profiles() -> dict[str, Any]:
    try:
        profiles_path = Path(PROFILES_PATH)
        profiles_path.mkdir(parents=True, exist_ok=True)
        loaded: list[str] = []
        if (profiles_path / "chanakya_profile.json").exists():
            loaded.append("chanakya")
        if (profiles_path / "aryabhata_profile.json").exists():
            loaded.append("aryabhata")
        return {"status": "ok", "loaded": loaded}
    except Exception as exc:
        logger.exception("Startup profile reload failed")
        return {"status": "error", "detail": str(exc)}


async def verify_latest_backup() -> dict[str, Any]:
    try:
        backup_path = Path(BACKUPS_PATH)
        backup_path.mkdir(parents=True, exist_ok=True)
        backups = sorted(backup_path.glob("patchwise_*.db"), reverse=True)
        if backups:
            return {"status": "ok", "latest_backup": backups[0].name}
        return {"status": "no_backup", "detail": "No backups found yet"}
    except Exception as exc:
        logger.exception("Startup backup check failed")
        return {"status": "error", "detail": str(exc)}
