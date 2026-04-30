from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class PatchSQLStore:
    def __init__(self, db_path: str = "./data/sqlite/patchwise.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS patch_sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    subsystem TEXT,
                    rounds INTEGER,
                    verdict TEXT,
                    quality_score REAL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS review_findings (
                    finding_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    round INTEGER,
                    issue_type TEXT,
                    severity TEXT,
                    description TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS fix_patterns (
                    pattern_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    issue_type TEXT,
                    subsystem TEXT,
                    fix_approach TEXT,
                    success_count INTEGER DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS similar_patch_refs (
                    ref_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    title TEXT,
                    url TEXT,
                    author TEXT,
                    relevance_score REAL
                )
                """
            )

    def save_session(self, session_state: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO patch_sessions
                    (session_id, subsystem, rounds, verdict, quality_score)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    session_state.get("session_id"),
                    session_state.get("subsystem", "alsa-asoc"),
                    int(session_state.get("current_round", 1)),
                    session_state.get("verdict", "PENDING"),
                    float(session_state.get("quality_score", 0.0)),
                ),
            )

    def save_findings(self, session_state: dict[str, Any]) -> None:
        with self._connect() as conn:
            for round_item in session_state.get("review_findings", []):
                round_id = int(round_item.get("round", 0))
                for finding in round_item.get("findings", []):
                    conn.execute(
                        """
                        INSERT INTO review_findings
                            (session_id, round, issue_type, severity, description)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            session_state.get("session_id"),
                            round_id,
                            finding.get("issue_type", "UNKNOWN"),
                            finding.get("severity", "INFO"),
                            finding.get("description", ""),
                        ),
                    )

    def save_fix_patterns(self, session_state: dict[str, Any]) -> None:
        subsystem = session_state.get("subsystem", "alsa-asoc")
        with self._connect() as conn:
            for fix_round in session_state.get("fix_attempts", []):
                for fix in fix_round.get("fixes", []):
                    card = fix.get("detailed_card", {})
                    issue = card.get("issue", "UNKNOWN")
                    approach = card.get("fix_approach", "")

                    cursor = conn.execute(
                        """
                        SELECT pattern_id, success_count
                        FROM fix_patterns
                        WHERE issue_type = ? AND subsystem = ? AND fix_approach = ?
                        """,
                        (issue, subsystem, approach),
                    )
                    row = cursor.fetchone()
                    if row:
                        conn.execute(
                            """
                            UPDATE fix_patterns
                            SET success_count = ?
                            WHERE pattern_id = ?
                            """,
                            (int(row[1]) + 1, int(row[0])),
                        )
                    else:
                        conn.execute(
                            """
                            INSERT INTO fix_patterns
                                (issue_type, subsystem, fix_approach, success_count)
                            VALUES (?, ?, ?, 1)
                            """,
                            (issue, subsystem, approach),
                        )

    def save_similar_refs(self, session_state: dict[str, Any]) -> None:
        with self._connect() as conn:
            for ref in session_state.get("similar_patches", []):
                conn.execute(
                    """
                    INSERT INTO similar_patch_refs
                        (session_id, title, url, author, relevance_score)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        session_state.get("session_id"),
                        ref.get("title", "unknown"),
                        ref.get("url", ""),
                        ref.get("author", "unknown"),
                        float(ref.get("relevance_score", 0.0)),
                    ),
                )

    def update_from_session(self, session_state: dict[str, Any]) -> None:
        self.save_session(session_state)
        self.save_findings(session_state)
        self.save_fix_patterns(session_state)
        self.save_similar_refs(session_state)
