from __future__ import annotations

import json
import os
import sqlite3
import uuid
import hashlib
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cli_kb_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern_key TEXT UNIQUE NOT NULL,
                    scope TEXT NOT NULL,
                    subsystem TEXT NOT NULL,
                    issue_type TEXT NOT NULL,
                    pattern_json TEXT NOT NULL DEFAULT '{}',
                    state TEXT NOT NULL DEFAULT 'candidate',
                    success_count INTEGER NOT NULL DEFAULT 0,
                    failure_count INTEGER NOT NULL DEFAULT 0,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_used TEXT,
                    last_promoted TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cli_kb_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    pattern_key TEXT NOT NULL,
                    round_num INTEGER NOT NULL DEFAULT 0,
                    applied INTEGER NOT NULL DEFAULT 0,
                    outcome TEXT NOT NULL,
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
                    getattr(payload["message_type"], "value", str(payload["message_type"])),
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

    def _next_pattern_state(self, success_count: int, failure_count: int) -> str:
        if success_count >= 3 and failure_count == 0:
            return "promoted"
        if success_count >= 1 and failure_count <= 1:
            return "probation"
        if failure_count >= 2 and success_count == 0:
            return "deprecated"
        return "candidate"

    def _upsert_pattern(
        self,
        *,
        scope: str,
        subsystem: str,
        issue_type: str,
        pattern_key: str,
        pattern: dict[str, Any],
        success: bool,
    ) -> None:
        now = _utc_now()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT success_count, failure_count FROM cli_kb_patterns WHERE pattern_key = ?",
                (pattern_key,),
            ).fetchone()
            success_count = int((row["success_count"] if row else 0) or 0)
            failure_count = int((row["failure_count"] if row else 0) or 0)
            if success:
                success_count += 1
            else:
                failure_count += 1
            total = max(1, success_count + failure_count)
            confidence = float(success_count) / float(total)
            next_state = self._next_pattern_state(success_count, failure_count)
            conn.execute(
                """
                INSERT INTO cli_kb_patterns (
                    pattern_key, scope, subsystem, issue_type, pattern_json, state,
                    success_count, failure_count, confidence, created_at, updated_at, last_used, last_promoted
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(pattern_key) DO UPDATE SET
                    pattern_json=excluded.pattern_json,
                    state=excluded.state,
                    success_count=excluded.success_count,
                    failure_count=excluded.failure_count,
                    confidence=excluded.confidence,
                    updated_at=excluded.updated_at,
                    last_used=excluded.last_used,
                    last_promoted=excluded.last_promoted
                """,
                (
                    pattern_key,
                    scope,
                    subsystem,
                    issue_type,
                    json.dumps(pattern, ensure_ascii=False, default=str),
                    next_state,
                    success_count,
                    failure_count,
                    confidence,
                    now,
                    now,
                    now,
                    now if next_state == "promoted" else None,
                ),
            )

    def _pattern_key(self, subsystem: str, issue_type: str, fix_text: str, scope: str) -> str:
        digest = hashlib.sha1(f"{issue_type}|{fix_text[:180]}".encode("utf-8", errors="ignore")).hexdigest()[:14]
        if scope == "global":
            return f"global::{issue_type}::{digest}"
        return f"subsystem::{subsystem}::{issue_type}::{digest}"

    def _normalize_fix_text(self, fix_text: str) -> str:
        collapsed = " ".join(str(fix_text or "").split())
        return collapsed.strip()

    def _is_low_quality_fix(self, issue_type: str, fix_text: str, status: str) -> bool:
        allowed_issue_types = {"STYLE", "LOGIC", "MEMORY", "COMPLIANCE", "COMMIT", "COVER_LETTER"}
        if issue_type not in allowed_issue_types:
            return True
        if status not in {"FIXED", "APPLIED"}:
            return True
        normalized = self._normalize_fix_text(fix_text)
        if len(normalized) < 8 or len(normalized) > 1200:
            return True
        lowered = normalized.lower()
        noisy_markers = {
            "placeholder",
            "todo",
            "tbd",
            "fixme",
            "n/a",
            "no change required",
            "same as before",
        }
        if any(marker in lowered for marker in noisy_markers):
            return True
        return False

    def learn_from_session(self, session_id: str, state_json: dict[str, Any], subsystem: str) -> dict[str, Any]:
        fix_attempts = state_json.get("fix_attempts") if isinstance(state_json.get("fix_attempts"), list) else []
        verdict = str(state_json.get("verdict", "NEEDS_WORK"))
        quality_score = float(state_json.get("quality_score", 0.0) or 0.0)
        success = verdict == "LGTM"
        should_learn = success or quality_score >= 85.0
        patterns_seen: set[str] = set()
        fix_signatures_seen: set[str] = set()
        skipped_low_quality = 0
        learned = 0

        if not should_learn:
            return {
                "learned_patterns": 0,
                "unique_patterns": 0,
                "verdict": verdict,
                "skipped_low_quality": 0,
                "learning_mode": "disabled",
                "reason": "quality_gate_not_met",
            }

        for attempt in fix_attempts:
            fixes = attempt.get("fixes") if isinstance(attempt, dict) and isinstance(attempt.get("fixes"), list) else []
            for fix in fixes:
                if not isinstance(fix, dict):
                    continue
                issue_type = str(fix.get("category", "STYLE") or "STYLE")
                fix_text = str(fix.get("fix", "") or "")
                fix_status = str(fix.get("status", "") or "").upper()
                if not fix_text:
                    skipped_low_quality += 1
                    continue
                if self._is_low_quality_fix(issue_type, fix_text, fix_status):
                    skipped_low_quality += 1
                    continue
                normalized_fix = self._normalize_fix_text(fix_text)
                signature = hashlib.sha1(
                    f"{subsystem}|{issue_type}|{normalized_fix[:220]}".encode("utf-8", errors="ignore")
                ).hexdigest()
                if signature in fix_signatures_seen:
                    # Prevent duplicate increments when same fix appears repeatedly in one session.
                    continue
                fix_signatures_seen.add(signature)
                pattern_payload = {
                    "issue_type": issue_type,
                    "fix": normalized_fix,
                    "problem": str(fix.get("problem", "") or ""),
                    "status": fix_status,
                    "subsystem": subsystem,
                    "quality_score": quality_score,
                }
                for scope in ("subsystem", "global"):
                    key = self._pattern_key(subsystem, issue_type, normalized_fix, scope=scope)
                    self._upsert_pattern(
                        scope=scope,
                        subsystem=subsystem,
                        issue_type=issue_type,
                        pattern_key=key,
                        pattern=pattern_payload,
                        success=success,
                    )
                    patterns_seen.add(key)
                    learned += 1

        if patterns_seen:
            with self._conn() as conn:
                for key in sorted(patterns_seen):
                    conn.execute(
                        """
                        INSERT INTO cli_kb_usage (session_id, pattern_key, round_num, applied, outcome, created_at)
                        VALUES (?, ?, ?, 1, ?, ?)
                        """,
                        (
                            session_id,
                            key,
                            int(state_json.get("current_round", 0) or 0),
                            verdict,
                            _utc_now(),
                        ),
                    )
        return {
            "learned_patterns": learned,
            "unique_patterns": len(patterns_seen),
            "verdict": verdict,
            "skipped_low_quality": skipped_low_quality,
            "learning_mode": "strict_quality_gate",
        }

    def get_active_kb_patterns(self, subsystem: str, limit: int = 12) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT pattern_key, scope, subsystem, issue_type, pattern_json, state, success_count,
                       failure_count, confidence, last_used, last_promoted
                FROM cli_kb_patterns
                WHERE state IN ('promoted', 'probation')
                  AND (
                      (scope = 'subsystem' AND subsystem = ?)
                      OR scope = 'global'
                  )
                ORDER BY
                  CASE state WHEN 'promoted' THEN 0 ELSE 1 END ASC,
                  CASE scope WHEN 'subsystem' THEN 0 ELSE 1 END ASC,
                  confidence DESC,
                  success_count DESC
                LIMIT ?
                """,
                (subsystem, int(limit)),
            ).fetchall()
        output: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["pattern"] = json.loads(item.pop("pattern_json", "{}") or "{}")
            output.append(item)
        return output

    def list_kb_patterns(self, subsystem: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        query = (
            "SELECT pattern_key, scope, subsystem, issue_type, pattern_json, state, success_count, "
            "failure_count, confidence, created_at, updated_at, last_used, last_promoted "
            "FROM cli_kb_patterns"
        )
        params: list[Any] = []
        if subsystem:
            query += " WHERE subsystem = ? OR scope = 'global'"
            params.append(subsystem)
        query += " ORDER BY confidence DESC, success_count DESC, updated_at DESC LIMIT ?"
        params.append(int(limit))
        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
        output: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["pattern"] = json.loads(item.pop("pattern_json", "{}") or "{}")
            output.append(item)
        return output

    def kb_stats(self) -> dict[str, Any]:
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) AS c FROM cli_kb_patterns").fetchone()["c"]
            promoted = conn.execute("SELECT COUNT(*) AS c FROM cli_kb_patterns WHERE state = 'promoted'").fetchone()["c"]
            probation = conn.execute("SELECT COUNT(*) AS c FROM cli_kb_patterns WHERE state = 'probation'").fetchone()["c"]
            deprecated = conn.execute("SELECT COUNT(*) AS c FROM cli_kb_patterns WHERE state = 'deprecated'").fetchone()["c"]
            globals_count = conn.execute("SELECT COUNT(*) AS c FROM cli_kb_patterns WHERE scope = 'global'").fetchone()["c"]
            subsystem_count = conn.execute("SELECT COUNT(*) AS c FROM cli_kb_patterns WHERE scope = 'subsystem'").fetchone()["c"]
            usage_count = conn.execute("SELECT COUNT(*) AS c FROM cli_kb_usage").fetchone()["c"]
        return {
            "total_patterns": int(total or 0),
            "promoted": int(promoted or 0),
            "probation": int(probation or 0),
            "deprecated": int(deprecated or 0),
            "global_patterns": int(globals_count or 0),
            "subsystem_patterns": int(subsystem_count or 0),
            "usage_events": int(usage_count or 0),
        }

    def set_pattern_state(self, pattern_key: str, state: str) -> bool:
        if state not in {"candidate", "probation", "promoted", "deprecated"}:
            raise ValueError(f"invalid state: {state}")
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE cli_kb_patterns SET state = ?, updated_at = ?, last_promoted = ? WHERE pattern_key = ?",
                (
                    state,
                    _utc_now(),
                    _utc_now() if state == "promoted" else None,
                    pattern_key,
                ),
            )
            return int(cur.rowcount or 0) > 0
