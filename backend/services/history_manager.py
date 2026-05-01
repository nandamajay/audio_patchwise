from __future__ import annotations

import difflib
import json
import os
import sqlite3
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, Preformatted, SimpleDocTemplate, Spacer

DB_PATH = os.environ.get("SQLITE_PATH") or os.environ.get("SQLITE_DB_PATH") or "./data/sqlite/patchwise.db"
EXPORTS_ROOT = os.environ.get("PATCHWISE_EXPORTS_DIR", "./exports")
EXPORTS_DIR = Path(EXPORTS_ROOT)
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)


class HistoryManager:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = Path(db_path or DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        schema_path = Path(__file__).parent.parent / "db" / "history_schema.sql"
        if schema_path.exists():
            with self._conn() as conn:
                conn.executescript(schema_path.read_text())

    def create_session(
        self,
        patch: str,
        input_type: str,
        metadata: dict[str, Any],
        session_id: Optional[str] = None,
    ) -> str:
        sid = session_id or str(uuid.uuid4())
        title = self._extract_title(patch)
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO patch_sessions
                (id, created_at, updated_at, title, subsystem, kernel_version,
                 source_path, llm_model, max_rounds, input_type, original_patch)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    sid,
                    now,
                    now,
                    title,
                    metadata.get("subsystem", "ASoC"),
                    metadata.get("kernel_version"),
                    metadata.get("source_path"),
                    metadata.get("llm_model", "gpt-4o"),
                    metadata.get("max_rounds", 5),
                    input_type,
                    patch,
                ),
            )
        return sid

    def update_session(self, session_id: str, **kwargs: Any) -> None:
        if not kwargs:
            return
        kwargs["updated_at"] = datetime.now(timezone.utc).isoformat()
        cols = ", ".join(f"{k}=?" for k in kwargs)
        vals = [kwargs[k] for k in kwargs] + [session_id]
        with self._conn() as conn:
            conn.execute(f"UPDATE patch_sessions SET {cols} WHERE id=?", vals)

    def increment_interrupt(self, session_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE patch_sessions
                SET interrupt_count = COALESCE(interrupt_count, 0) + 1,
                    updated_at = ?
                WHERE id = ?
                """,
                (datetime.now(timezone.utc).isoformat(), session_id),
            )

    def get_session(self, session_id: str) -> Optional[dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM patch_sessions WHERE id=?", (session_id,)).fetchone()
            return dict(row) if row else None

    def list_sessions(
        self,
        filters: Optional[dict[str, Any]] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM patch_sessions WHERE 1=1"
        params: list[Any] = []
        if filters:
            if filters.get("subsystem"):
                query += " AND subsystem=?"
                params.append(filters["subsystem"])
            if filters.get("verdict"):
                query += " AND verdict=?"
                params.append(filters["verdict"])
            if filters.get("date_from"):
                query += " AND created_at >= ?"
                params.append(filters["date_from"])
            if filters.get("date_to"):
                query += " AND created_at <= ?"
                params.append(filters["date_to"])
        if search:
            query += " AND (title LIKE ? OR original_patch LIKE ?)"
            params += [f"%{search}%", f"%{search}%"]

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params += [limit, offset]

        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def save_round(
        self,
        session_id: str,
        round_number: int,
        chanakya_input: str,
        chanakya_output: dict[str, Any],
        aryabhata_input: dict[str, Any],
        aryabhata_output: dict[str, Any],
        previous_patch: str,
        current_patch: str,
        duration_secs: float,
        verdict: str,
    ) -> str:
        round_id = str(uuid.uuid4())
        diff = self._compute_diff(previous_patch, current_patch)
        issues_found = len(chanakya_output.get("issues", []))
        issues_fixed = int(aryabhata_output.get("fixed_count", 0) or 0)
        improvement = (issues_fixed / issues_found * 100) if issues_found else 0.0

        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO session_rounds
                (id, session_id, round_number, issues_found, issues_fixed,
                 improvement_pct, chanakya_input, chanakya_output,
                 aryabhata_input, aryabhata_output, round_diff,
                 duration_secs, verdict)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    round_id,
                    session_id,
                    round_number,
                    issues_found,
                    issues_fixed,
                    improvement,
                    chanakya_input,
                    json.dumps(chanakya_output),
                    json.dumps(aryabhata_input),
                    json.dumps(aryabhata_output),
                    diff,
                    duration_secs,
                    verdict,
                ),
            )
        return round_id

    def get_rounds(self, session_id: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM session_rounds WHERE session_id=? ORDER BY round_number",
                (session_id,),
            ).fetchall()
            result: list[dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                for field in ("chanakya_output", "aryabhata_input", "aryabhata_output"):
                    if item.get(field):
                        try:
                            item[field] = json.loads(item[field])
                        except Exception:
                            pass
                result.append(item)
            return result

    def save_message(
        self,
        session_id: str,
        agent: str,
        msg_type: str,
        content: str,
        round_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        msg_id = str(uuid.uuid4())
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO session_messages
                (id, session_id, round_id, agent, msg_type, content, metadata)
                VALUES (?,?,?,?,?,?,?)
                """,
                (msg_id, session_id, round_id, agent, msg_type, content, json.dumps(metadata or {})),
            )
        return msg_id

    def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM session_messages WHERE session_id=? ORDER BY created_at ASC",
                (session_id,),
            ).fetchall()
            result: list[dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                if item.get("metadata"):
                    try:
                        item["metadata"] = json.loads(item["metadata"])
                    except Exception:
                        pass
                result.append(item)
            return result

    def save_reference(self, session_id: str, round_id: Optional[str], ref: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO session_references
                (id, session_id, round_id, source, title, url, author,
                 date, similarity, subsystem, summary)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    str(uuid.uuid4()),
                    session_id,
                    round_id,
                    ref.get("source", "lkml"),
                    ref.get("title"),
                    ref.get("url"),
                    ref.get("author"),
                    ref.get("date"),
                    ref.get("similarity"),
                    ref.get("subsystem"),
                    ref.get("summary"),
                ),
            )

    def export_pdf(self, session_id: str) -> str:
        session = self.get_session(session_id)
        if not session:
            raise ValueError("Session not found")
        rounds = self.get_rounds(session_id)
        messages = self.get_messages(session_id)

        export_path = EXPORTS_DIR / f"patchwise_{session_id[:8]}_report.pdf"
        doc = SimpleDocTemplate(str(export_path), pagesize=A4)
        styles = getSampleStyleSheet()
        story: list[Any] = []

        story.append(Paragraph("PatchWise Review Report", styles["Title"]))
        story.append(Paragraph(f"Session: {session['title']}", styles["Heading2"]))
        story.append(Paragraph(f"Date: {session['created_at']}", styles["Normal"]))
        story.append(Paragraph(f"Verdict: {session['verdict']}", styles["Normal"]))
        story.append(Paragraph(f"Subsystem: {session['subsystem']}", styles["Normal"]))
        story.append(Spacer(1, 12))

        story.append(Paragraph("Original Patch", styles["Heading2"]))
        story.append(Preformatted((session.get("original_patch") or "")[:3000], styles["Code"]))
        story.append(Spacer(1, 12))

        for round_item in rounds:
            story.append(Paragraph(f"Round {round_item['round_number']}", styles["Heading2"]))
            story.append(
                Paragraph(
                    (
                        f"Issues Found: {round_item['issues_found']} | "
                        f"Fixed: {round_item['issues_fixed']} | "
                        f"Improvement: {round_item['improvement_pct']:.1f}% | "
                        f"Verdict: {round_item['verdict']}"
                    ),
                    styles["Normal"],
                )
            )
            if round_item.get("round_diff"):
                story.append(Paragraph("Diff:", styles["Heading3"]))
                story.append(Preformatted(round_item["round_diff"][:2000], styles["Code"]))
            story.append(Spacer(1, 12))

        story.append(Paragraph("Full Conversation", styles["Heading2"]))
        for msg in messages:
            story.append(Paragraph(f"[{msg['agent']}] {msg['msg_type'].upper()}", styles["Heading3"]))
            story.append(Paragraph((msg.get("content") or "")[:1000], styles["Normal"]))
            story.append(Spacer(1, 6))

        if session.get("final_patch"):
            story.append(Paragraph("Final Fixed Patch", styles["Heading2"]))
            story.append(Preformatted((session.get("final_patch") or "")[:3000], styles["Code"]))

        doc.build(story)
        self._save_export_record(session_id, "pdf", str(export_path))
        return str(export_path)

    def export_markdown(self, session_id: str) -> str:
        session = self.get_session(session_id)
        if not session:
            raise ValueError("Session not found")
        rounds = self.get_rounds(session_id)
        messages = self.get_messages(session_id)

        md = "# PatchWise Review Report\n\n"
        md += f"**Session:** {session['title']}\n"
        md += f"**Date:** {session['created_at']}\n"
        md += f"**Verdict:** {session['verdict']}\n"
        md += f"**Subsystem:** {session['subsystem']}\n"
        md += f"**Rounds:** {session['total_rounds']}\n\n"
        md += f"---\n\n## Original Patch\n\n```diff\n{session['original_patch']}\n```\n\n"

        for round_item in rounds:
            md += f"---\n\n## Round {round_item['round_number']}\n\n"
            md += f"- Issues Found: {round_item['issues_found']}\n"
            md += f"- Issues Fixed: {round_item['issues_fixed']}\n"
            md += f"- Improvement: {round_item['improvement_pct']:.1f}%\n"
            md += f"- Verdict: {round_item['verdict']}\n\n"
            if round_item.get("round_diff"):
                md += f"### Diff\n\n```diff\n{round_item['round_diff']}\n```\n\n"

        md += "---\n\n## Full Conversation\n\n"
        for msg in messages:
            md += f"### [{msg['agent']}] {msg['msg_type'].upper()}\n\n"
            md += f"{msg['content']}\n\n"

        if session.get("final_patch"):
            md += f"---\n\n## Final Fixed Patch\n\n```diff\n{session['final_patch']}\n```\n"

        export_path = EXPORTS_DIR / f"patchwise_{session_id[:8]}_report.md"
        export_path.write_text(md)
        self._save_export_record(session_id, "markdown", str(export_path))
        return str(export_path)

    def export_patch(self, session_id: str) -> str:
        session = self.get_session(session_id)
        if not session:
            raise ValueError("Session not found")
        export_path = EXPORTS_DIR / f"patchwise_{session_id[:8]}_fixed.patch"
        export_path.write_text(session.get("final_patch") or "")
        self._save_export_record(session_id, "patch", str(export_path))
        return str(export_path)

    def export_zip(self, session_id: str) -> str:
        pdf_path = self.export_pdf(session_id)
        md_path = self.export_markdown(session_id)
        patch_path = self.export_patch(session_id)

        zip_path = EXPORTS_DIR / f"patchwise_{session_id[:8]}_complete.zip"
        with zipfile.ZipFile(zip_path, "w") as zip_file:
            zip_file.write(pdf_path, Path(pdf_path).name)
            zip_file.write(md_path, Path(md_path).name)
            zip_file.write(patch_path, Path(patch_path).name)

        self._save_export_record(session_id, "zip", str(zip_path))
        return str(zip_path)

    def get_session_analytics(self, session_id: str) -> dict[str, Any]:
        rounds = self.get_rounds(session_id)
        session = self.get_session(session_id)
        if not session:
            raise ValueError("Session not found")

        issues_found = int(session.get("total_issues_found") or 0)
        issues_fixed = int(session.get("total_issues_fixed") or 0)
        return {
            "session_id": session_id,
            "title": session["title"],
            "verdict": session["verdict"],
            "total_rounds": len(rounds),
            "total_issues_found": issues_found,
            "total_issues_fixed": issues_fixed,
            "fix_rate": (issues_fixed / issues_found * 100) if issues_found else 0,
            "rounds_detail": [
                {
                    "round": round_item["round_number"],
                    "issues_found": round_item["issues_found"],
                    "issues_fixed": round_item["issues_fixed"],
                    "improvement_pct": round_item["improvement_pct"],
                    "verdict": round_item["verdict"],
                    "duration_secs": round_item["duration_secs"],
                }
                for round_item in rounds
            ],
        }

    def get_global_stats(self) -> dict[str, Any]:
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM patch_sessions").fetchone()[0]
            lgtm = conn.execute(
                "SELECT COUNT(*) FROM patch_sessions WHERE verdict='LGTM'"
            ).fetchone()[0]
            avg_rounds = conn.execute(
                "SELECT AVG(total_rounds) FROM patch_sessions WHERE verdict='LGTM'"
            ).fetchone()[0] or 0
            kb_count = conn.execute(
                "SELECT COUNT(*) FROM patch_sessions WHERE kb_contributed=1"
            ).fetchone()[0]

        return {
            "total_sessions": total,
            "lgtm_sessions": lgtm,
            "success_rate": (lgtm / total * 100) if total else 0,
            "avg_rounds_to_lgtm": round(avg_rounds, 1),
            "kb_contributions": kb_count,
        }

    def _extract_title(self, patch: str) -> str:
        for line in patch.splitlines():
            if line.startswith("Subject:"):
                return line.replace("Subject:", "").strip()[:120]
            if line.startswith("[PATCH"):
                return line.strip()[:120]
        return f"Patch Session {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}"

    def _compute_diff(self, original: str, fixed: str) -> str:
        if not original or not fixed:
            return ""

        diff = difflib.unified_diff(
            original.splitlines(keepends=True),
            fixed.splitlines(keepends=True),
            fromfile="original.patch",
            tofile="fixed.patch",
        )
        return "".join(list(diff)[:200])

    def _save_export_record(self, session_id: str, export_type: str, path: str) -> None:
        file_path = Path(path)
        size = file_path.stat().st_size if file_path.exists() else 0
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO session_exports (id, session_id, export_type, file_path, file_size)
                VALUES (?,?,?,?,?)
                """,
                (str(uuid.uuid4()), session_id, export_type, path, size),
            )


history_manager = HistoryManager()
