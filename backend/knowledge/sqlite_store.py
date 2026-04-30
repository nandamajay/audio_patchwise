from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional


class SQLiteStore:
    def __init__(self, db_path: str = "./data/sqlite/patchwise.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        schema_file = Path(__file__).with_name("schema.sql")
        with self._get_conn() as conn:
            if schema_file.exists():
                conn.executescript(schema_file.read_text())
            else:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sessions (
                        session_id TEXT PRIMARY KEY,
                        status TEXT NOT NULL DEFAULT 'pending',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        patch_input TEXT,
                        context TEXT,
                        config TEXT,
                        current_round INTEGER DEFAULT 0,
                        max_rounds INTEGER DEFAULT 5,
                        conversation TEXT,
                        issues_found TEXT,
                        final_patch TEXT,
                        review_report TEXT,
                        verdict TEXT,
                        submission TEXT
                    )
                    """
                )

    def save_session(self, snapshot: dict) -> None:
        conn = self._get_conn()
        conn.execute(
            """
            INSERT OR REPLACE INTO sessions (
                session_id, status, created_at, updated_at,
                patch_input, context, config, current_round,
                max_rounds, conversation, issues_found,
                final_patch, review_report, verdict, submission
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                snapshot["session_id"],
                snapshot["status"],
                snapshot["created_at"],
                snapshot["updated_at"],
                json.dumps(snapshot["patch_input"]),
                json.dumps(snapshot["context"]),
                json.dumps(snapshot["config"]),
                snapshot["current_round"],
                snapshot["max_rounds"],
                json.dumps(snapshot["conversation"]),
                json.dumps(snapshot["issues_found"]),
                snapshot.get("final_patch"),
                json.dumps(snapshot.get("review_report")),
                snapshot.get("verdict"),
                json.dumps(snapshot.get("submission")),
            ),
        )
        conn.commit()
        conn.close()

    def get_session(self, session_id: str) -> Optional[dict]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        conn.close()
        if row:
            data = dict(row)
            json_fields = [
                "patch_input",
                "context",
                "config",
                "conversation",
                "issues_found",
                "review_report",
                "submission",
            ]
            for field in json_fields:
                raw = data.get(field)
                if not raw:
                    data[field] = {} if field in {"patch_input", "context", "config", "review_report", "submission"} else []
                else:
                    data[field] = json.loads(raw)
            return data
        return None

    def update_session(self, session_id: str, fields: dict) -> None:
        if not fields:
            return

        set_clause = ", ".join(f"{key} = ?" for key in fields)
        values = [json.dumps(value) if isinstance(value, (dict, list)) else value for value in fields.values()]
        values.append(session_id)

        conn = self._get_conn()
        conn.execute(f"UPDATE sessions SET {set_clause} WHERE session_id = ?", values)
        conn.commit()
        conn.close()

    def list_sessions(self, limit: int = 50) -> list:
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT session_id, status, created_at, updated_at,
                   current_round, max_rounds, verdict,
                   json_extract(context, '$.subsystem') as subsystem,
                   json_extract(patch_input, '$.raw_text') as patch_preview
            FROM sessions
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def delete_session(self, session_id: str) -> None:
        conn = self._get_conn()
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        conn.commit()
        conn.close()
