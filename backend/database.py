"""
Thread-safe SQLite with WAL mode + connection pooling.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(
    os.environ.get("SQLITE_PATH")
    or os.environ.get("SQLITE_DB_PATH")
    or "data/patchwise.db"
)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_local = threading.local()
_write_lock = threading.Lock()


def _is_connection_usable(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("SELECT 1")
        return True
    except Exception:
        return False


def get_db_connection() -> sqlite3.Connection:
    """
    Return a thread-local connection configured for concurrent access.
    """
    conn = getattr(_local, "connection", None)
    if conn is None or not _is_connection_usable(conn):
        conn = sqlite3.connect(
            str(DB_PATH),
            check_same_thread=False,
            timeout=10.0,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-64000")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA temp_store=MEMORY")
        _local.connection = conn
    return conn


@contextmanager
def get_write_connection():
    """
    Context manager for serialized write operations.
    """
    conn = get_db_connection()
    with _write_lock:
        try:
            yield conn
            conn.commit()
        except Exception as exc:
            conn.rollback()
            logger.error("[DB] Write failed, rolled back: %s", exc)
            raise


def init_db() -> None:
    """Initialise all required tables."""
    conn = get_db_connection()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            patch_title TEXT,
            subsystem TEXT DEFAULT 'audio',
            status TEXT DEFAULT 'active',
            verdict TEXT,
            rounds_completed INTEGER DEFAULT 0,
            total_issues_found INTEGER DEFAULT 0,
            total_issues_fixed INTEGER DEFAULT 0,
            llm_model TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            user_id TEXT DEFAULT 'default'
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            agent TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            round_number INTEGER DEFAULT 1,
            thinking_steps TEXT,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS review_issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            round_number INTEGER NOT NULL,
            issue_type TEXT NOT NULL,
            description TEXT NOT NULL,
            line_number INTEGER,
            severity TEXT DEFAULT 'warning',
            status TEXT DEFAULT 'open',
            fix_applied TEXT,
            confidence REAL DEFAULT 0.0,
            upvotes INTEGER DEFAULT 0,
            downvotes INTEGER DEFAULT 0,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS diffs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            round_number INTEGER NOT NULL,
            original_patch TEXT NOT NULL,
            fixed_patch TEXT NOT NULL,
            diff_output TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS seed_run_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            status TEXT NOT NULL,
            patches_fetched INTEGER DEFAULT 0,
            duration_seconds REAL DEFAULT 0,
            error TEXT,
            run_at TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_base (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subsystem TEXT NOT NULL,
            issue_type TEXT NOT NULL,
            pattern TEXT NOT NULL,
            fix_pattern TEXT,
            source TEXT,
            upvotes INTEGER DEFAULT 0,
            downvotes INTEGER DEFAULT 0,
            confidence REAL DEFAULT 0.5,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    collab_schema_path = Path(__file__).with_name("database_schema_collab.sql")
    if collab_schema_path.exists():
        conn.executescript(collab_schema_path.read_text())

    conn.commit()
    logger.info("[DB] Database initialised with WAL mode")


def get_db():
    """Generator-compatible DB accessor for FastAPI dependencies."""
    conn = get_db_connection()
    try:
        yield conn
    finally:
        # Thread-local pooled connection is intentionally kept open.
        pass
