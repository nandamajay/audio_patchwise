from __future__ import annotations

import os
import sqlite3
import subprocess
from datetime import datetime, timezone
from typing import Any

import chromadb


class HealthMonitor:
    """Collect system health metrics for the dashboard."""

    def __init__(
        self,
        db_path: str = os.environ.get("SQLITE_PATH") or os.environ.get("SQLITE_DB_PATH") or "./data/sqlite/patchwise.db",
        chroma_path: str = os.environ.get("CHROMADB_PATH", "./data/chromadb"),
    ):
        self.db_path = db_path
        self.chroma_path = chroma_path

    def get_full_health(self) -> dict[str, Any]:
        return {
            "chromadb": self._check_chromadb(),
            "sqlite": self._check_sqlite(),
            "lkml_seeder": self._check_lkml_seeder(),
            "agent_perf": self._check_agent_performance(),
            "feedback_stats": self._check_feedback_stats(),
            "services": self._check_services(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _check_chromadb(self) -> dict[str, Any]:
        try:
            client = chromadb.PersistentClient(path=self.chroma_path)
            kb_collection = client.get_or_create_collection("kernel_patches")
            fb_collection = client.get_or_create_collection("feedback_patterns")

            size_bytes = 0
            if os.path.exists(self.chroma_path):
                for name in os.listdir(self.chroma_path):
                    candidate = os.path.join(self.chroma_path, name)
                    if os.path.isfile(candidate):
                        size_bytes += os.path.getsize(candidate)

            return {
                "status": "healthy",
                "total_vectors": kb_collection.count(),
                "feedback_vectors": fb_collection.count(),
                "storage_mb": round(size_bytes / 1024 / 1024, 2),
                "path": self.chroma_path,
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def _check_sqlite(self) -> dict[str, Any]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                sessions = self._safe_count(conn, "sessions")
                patches = self._safe_count(conn, "patches")
                kb_count = self._safe_count(conn, "knowledge_base")
                feedbacks = self._safe_count(conn, "feedback")

            size_bytes = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
            return {
                "status": "healthy",
                "sessions": sessions,
                "patches": patches,
                "kb_entries": kb_count,
                "feedback": feedbacks,
                "storage_mb": round(size_bytes / 1024 / 1024, 2),
                "path": self.db_path,
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def _check_lkml_seeder(self) -> dict[str, Any]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    """
                    SELECT status, started_at, completed_at, patches_fetched, error_message
                    FROM seeder_log ORDER BY started_at DESC LIMIT 1
                    """
                ).fetchone()
            if row:
                return {
                    "status": row[0],
                    "last_run": row[1],
                    "completed_at": row[2],
                    "patches_fetched": row[3],
                    "error": row[4],
                }
            return {"status": "never_run", "last_run": None, "patches_fetched": 0}
        except Exception:
            return {"status": "unknown", "last_run": None}

    def _check_agent_performance(self) -> dict[str, Any]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                avg_rounds = conn.execute(
                    "SELECT AVG(total_rounds) FROM sessions WHERE verdict = 'LGTM'"
                ).fetchone()[0]
                lgtm_count = conn.execute(
                    "SELECT COUNT(*) FROM sessions WHERE verdict = 'LGTM'"
                ).fetchone()[0]
                max_rounds_count = conn.execute(
                    "SELECT COUNT(*) FROM sessions WHERE verdict = 'MAX_ROUNDS'"
                ).fetchone()[0]
                top_issues = conn.execute(
                    """
                    SELECT issue_type, COUNT(*) as cnt
                    FROM review_issues
                    GROUP BY issue_type ORDER BY cnt DESC LIMIT 5
                    """
                ).fetchall()
            return {
                "avg_rounds_to_lgtm": round(avg_rounds or 0, 1),
                "lgtm_sessions": lgtm_count,
                "max_round_sessions": max_rounds_count,
                "top_issue_types": [{"type": row[0], "count": row[1]} for row in top_issues],
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def _check_feedback_stats(self) -> dict[str, Any]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                total_up = conn.execute("SELECT COUNT(*) FROM feedback WHERE vote = 1").fetchone()[0]
                total_down = conn.execute("SELECT COUNT(*) FROM feedback WHERE vote = -1").fetchone()[0]
                top = conn.execute(
                    """
                    SELECT agent, issue_type, net_score, sample_text
                    FROM feedback_summary ORDER BY net_score DESC LIMIT 5
                    """
                ).fetchall()
            return {
                "total_upvotes": total_up,
                "total_downvotes": total_down,
                "net_score": total_up - total_down,
                "top_patterns": [
                    {"agent": row[0], "issue_type": row[1], "net_score": row[2], "sample": row[3]}
                    for row in top
                ],
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def _check_services(self) -> dict[str, str]:
        checks = {
            "FastAPI": "curl -sf http://localhost:8000/health",
            "ChromaDB": "curl -sf http://localhost:8001/api/v1/heartbeat",
            "sendmail": "which sendmail",
        }
        services: dict[str, str] = {}
        for name, cmd in checks.items():
            result = subprocess.run(cmd, shell=True, capture_output=True, check=False)
            services[name] = "healthy" if result.returncode == 0 else "unavailable"
        return services

    def _safe_count(self, conn: sqlite3.Connection, table: str) -> int:
        try:
            return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except Exception:
            return 0
