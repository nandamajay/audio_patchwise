from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Optional


class SQLiteStore:
    def __init__(
        self,
        db_path: str = (
            os.getenv("SQLITE_PATH")
            or os.getenv("SQLITE_DB_PATH")
            or "./data/sqlite/patchwise.db"
        ),
    ) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
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
            self._repair_legacy_session_foreign_keys(conn)

    def _repair_legacy_session_foreign_keys(self, conn: sqlite3.Connection) -> None:
        """
        Repair legacy tables that still reference sessions(id) from older schema versions.
        Current primary key is sessions(session_id), and foreign key mismatch causes
        POST /api/session/start to fail with sqlite3.OperationalError.
        """
        legacy_ref = "REFERENCES sessions(id)"
        fixed_ref = "REFERENCES sessions(session_id)"

        rows = conn.execute(
            """
            SELECT name, sql
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            """
        ).fetchall()

        to_rebuild: list[tuple[str, str]] = []
        for row in rows:
            name = row["name"] if isinstance(row, sqlite3.Row) else row[0]
            sql = row["sql"] if isinstance(row, sqlite3.Row) else row[1]
            if sql and legacy_ref in sql:
                to_rebuild.append((name, sql))

        if not to_rebuild:
            return

        conn.execute("PRAGMA foreign_keys=OFF")
        try:
            for table_name, create_sql in to_rebuild:
                temp_name = f"{table_name}__fkfix"
                rewritten = create_sql.replace(legacy_ref, fixed_ref)
                rewritten = rewritten.replace(
                    f"CREATE TABLE {table_name}",
                    f"CREATE TABLE {temp_name}",
                    1,
                )

                conn.execute(rewritten)

                cols = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
                col_names = [col["name"] if isinstance(col, sqlite3.Row) else col[1] for col in cols]
                quoted = ", ".join([f'"{col}"' for col in col_names])

                conn.execute(
                    f'INSERT INTO "{temp_name}" ({quoted}) SELECT {quoted} FROM "{table_name}"'
                )
                conn.execute(f'DROP TABLE "{table_name}"')
                conn.execute(f'ALTER TABLE "{temp_name}" RENAME TO "{table_name}"')
        finally:
            conn.execute("PRAGMA foreign_keys=ON")

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
