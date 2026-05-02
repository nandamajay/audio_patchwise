from __future__ import annotations

import json
import os
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pw_cli.protocol import A2AEnvelope


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CLISession:
    session_id: str
    status: str
    input_type: str
    input_ref: str
    subsystem: str
    created_at: str
    updated_at: str
    current_round: int
    max_rounds: int
    verdict: str
    summary: dict[str, Any]
    state_json: dict[str, Any]


class CLISessionStore:
    def __init__(self, db_path: str | None = None):
        resolved_path = (
            db_path
            or os.getenv("SQLITE_PATH")
            or os.getenv("SQLITE_DB_PATH")
            or "./data/sqlite/patchwise.db"
        )
        self.db_path = Path(resolved_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cli_sessions (
                    session_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    input_type TEXT NOT NULL,
                    input_ref TEXT NOT NULL,
                    subsystem TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    current_round INTEGER NOT NULL DEFAULT 0,
                    max_rounds INTEGER NOT NULL DEFAULT 5,
                    verdict TEXT NOT NULL DEFAULT 'PENDING',
                    summary_json TEXT NOT NULL DEFAULT '{}',
                    state_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cli_rounds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    round_num INTEGER NOT NULL,
                    phase TEXT NOT NULL,
                    summary_json TEXT NOT NULL DEFAULT '{}',
                    state_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    UNIQUE(session_id, round_num, phase)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cli_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    round_num INTEGER NOT NULL,
                    sender TEXT NOT NULL,
                    receiver TEXT NOT NULL,
                    message_type TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    issue_id TEXT,
                    confidence_score REAL NOT NULL DEFAULT 0.0,
                    content TEXT NOT NULL DEFAULT '',
                    evidence_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                )
                """
            )

    def create_session(
        self,
        input_type: str,
        input_ref: str,
        subsystem: str,
        max_rounds: int,
        state_json: dict[str, Any],
    ) -> str:
        session_id = str(uuid.uuid4())
        now = _utc_now()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO cli_sessions (
                    session_id, status, input_type, input_ref, subsystem,
                    created_at, updated_at, current_round, max_rounds, verdict,
                    summary_json, state_json
                ) VALUES (?, 'running', ?, ?, ?, ?, ?, 1, ?, 'PENDING', '{}', ?)
                """,
                (
                    session_id,
                    input_type,
                    input_ref,
                    subsystem,
                    now,
                    now,
                    int(max_rounds),
                    json.dumps(state_json, ensure_ascii=False, default=str),
                ),
            )
        return session_id

    def update_session(
        self,
        session_id: str,
        *,
        status: str | None = None,
        current_round: int | None = None,
        verdict: str | None = None,
        summary: dict[str, Any] | None = None,
        state_json: dict[str, Any] | None = None,
    ) -> None:
        fields: list[str] = ["updated_at = ?"]
        values: list[Any] = [_utc_now()]
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if current_round is not None:
            fields.append("current_round = ?")
            values.append(int(current_round))
        if verdict is not None:
            fields.append("verdict = ?")
            values.append(verdict)
        if summary is not None:
            fields.append("summary_json = ?")
            values.append(json.dumps(summary, ensure_ascii=False, default=str))
        if state_json is not None:
            fields.append("state_json = ?")
            values.append(json.dumps(state_json, ensure_ascii=False, default=str))
        values.append(session_id)
        with self._conn() as conn:
            conn.execute(f"UPDATE cli_sessions SET {', '.join(fields)} WHERE session_id = ?", values)

    def append_round(
        self,
        session_id: str,
        round_num: int,
        phase: str,
        summary: dict[str, Any],
        state_json: dict[str, Any],
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO cli_rounds (session_id, round_num, phase, summary_json, state_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, round_num, phase) DO UPDATE SET
                    summary_json=excluded.summary_json,
                    state_json=excluded.state_json,
                    created_at=excluded.created_at
                """,
                (
                    session_id,
                    int(round_num),
                    phase,
                    json.dumps(summary, ensure_ascii=False, default=str),
                    json.dumps(state_json, ensure_ascii=False, default=str),
                    _utc_now(),
                ),
            )

    def append_message(self, message: A2AEnvelope) -> None:
        payload = asdict(message)
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO cli_messages (
                    session_id, round_num, sender, receiver, message_type,
                    task_type, source, issue_id, confidence_score, content,
                    evidence_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["session_id"],
                    int(payload["round_num"]),
                    payload["sender"],
                    payload["receiver"],
                    payload["message_type"],
                    payload["task_type"],
                    payload["source"],
                    payload.get("issue_id"),
                    float(payload.get("confidence_score") or 0.0),
                    payload.get("content", ""),
                    json.dumps(payload.get("evidence", {}), ensure_ascii=False, default=str),
                    payload.get("timestamp", _utc_now()),
                ),
            )

    def get_session(self, session_id: str) -> Optional[CLISession]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM cli_sessions WHERE session_id = ?", (session_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        return CLISession(
            session_id=data["session_id"],
            status=data["status"],
            input_type=data["input_type"],
            input_ref=data["input_ref"],
            subsystem=data["subsystem"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            current_round=int(data["current_round"] or 0),
            max_rounds=int(data["max_rounds"] or 0),
            verdict=data["verdict"],
            summary=json.loads(data.get("summary_json") or "{}"),
            state_json=json.loads(data.get("state_json") or "{}"),
        )

    def list_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT session_id, status, input_type, input_ref, subsystem, created_at, updated_at,
                       current_round, max_rounds, verdict, summary_json
                FROM cli_sessions
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        output: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["summary"] = json.loads(item.pop("summary_json", "{}") or "{}")
            output.append(item)
        return output

    def get_rounds(self, session_id: str, round_num: int | None = None) -> list[dict[str, Any]]:
        query = (
            "SELECT session_id, round_num, phase, summary_json, state_json, created_at "
            "FROM cli_rounds WHERE session_id = ?"
        )
        params: list[Any] = [session_id]
        if round_num is not None:
            query += " AND round_num = ?"
            params.append(int(round_num))
        query += " ORDER BY round_num ASC, phase ASC"
        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["summary"] = json.loads(item.pop("summary_json", "{}") or "{}")
            item["state"] = json.loads(item.pop("state_json", "{}") or "{}")
            result.append(item)
        return result

    def get_messages(self, session_id: str, limit: int = 400) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT session_id, round_num, sender, receiver, message_type, task_type, source,
                       issue_id, confidence_score, content, evidence_json, created_at
                FROM cli_messages
                WHERE session_id = ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (session_id, int(limit)),
            ).fetchall()
        output: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["evidence"] = json.loads(item.pop("evidence_json", "{}") or "{}")
            output.append(item)
        return output

