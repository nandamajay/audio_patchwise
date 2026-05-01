from __future__ import annotations

import os
import sqlite3
import uuid
from typing import Any, Optional

import chromadb


class FeedbackManager:
    """
    Upvote/downvote signals on agent messages.
    Positive signals receive higher retrieval weight in ChromaDB.
    """

    def __init__(
        self,
        db_path: str = os.environ.get("SQLITE_PATH") or os.environ.get("SQLITE_DB_PATH") or "./data/sqlite/patchwise.db",
        chroma_path: str = os.environ.get("CHROMADB_PATH", "./data/chromadb"),
    ):
        self.db_path = db_path
        self.chroma = chromadb.PersistentClient(path=chroma_path)
        self.collection = self.chroma.get_or_create_collection(
            name="feedback_patterns",
            metadata={"hnsw:space": "cosine"},
        )
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback (
                    id              TEXT PRIMARY KEY,
                    session_id      TEXT NOT NULL,
                    round_num       INTEGER NOT NULL,
                    agent           TEXT NOT NULL,
                    message_id      TEXT NOT NULL,
                    vote            INTEGER NOT NULL,
                    comment         TEXT,
                    message_content TEXT NOT NULL,
                    issue_type      TEXT,
                    subsystem       TEXT DEFAULT 'audio',
                    created_at      TEXT DEFAULT (datetime('now')),
                    embedding_id    TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback_summary (
                    pattern_id   TEXT PRIMARY KEY,
                    agent        TEXT,
                    issue_type   TEXT,
                    subsystem    TEXT,
                    upvotes      INTEGER DEFAULT 0,
                    downvotes    INTEGER DEFAULT 0,
                    net_score    INTEGER DEFAULT 0,
                    sample_text  TEXT,
                    last_updated TEXT
                )
                """
            )
            conn.commit()

    async def record_feedback(
        self,
        session_id: str,
        round_num: int,
        agent: str,
        message_id: str,
        message_content: str,
        vote: int,
        comment: Optional[str] = None,
        issue_type: Optional[str] = None,
        subsystem: str = "audio",
    ) -> dict[str, Any]:
        feedback_id = str(uuid.uuid4())

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO feedback
                (id, session_id, round_num, agent, message_id, vote, comment,
                 message_content, issue_type, subsystem)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    feedback_id,
                    session_id,
                    round_num,
                    agent,
                    message_id,
                    vote,
                    comment,
                    message_content,
                    issue_type,
                    subsystem,
                ),
            )
            conn.commit()

        weight = 1.5 if vote == 1 else 0.3
        try:
            self.collection.add(
                ids=[feedback_id],
                documents=[message_content],
                metadatas=[
                    {
                        "agent": agent,
                        "vote": str(vote),
                        "weight": str(weight),
                        "issue_type": issue_type or "general",
                        "subsystem": subsystem,
                        "session_id": session_id,
                        "round_num": str(round_num),
                    }
                ],
            )
        except Exception:
            pass

        self._update_summary(agent, issue_type or "general", subsystem, vote, message_content)
        return {"feedback_id": feedback_id, "recorded": True, "weight": weight}

    def _update_summary(
        self,
        agent: str,
        issue_type: str,
        subsystem: str,
        vote: int,
        sample_text: str,
    ) -> None:
        pattern_id = f"{agent}_{issue_type}_{subsystem}"

        with sqlite3.connect(self.db_path) as conn:
            existing = conn.execute(
                "SELECT pattern_id FROM feedback_summary WHERE pattern_id = ?",
                (pattern_id,),
            ).fetchone()

            if existing:
                conn.execute(
                    """
                    UPDATE feedback_summary
                    SET upvotes = upvotes + ?,
                        downvotes = downvotes + ?,
                        net_score = net_score + ?,
                        last_updated = datetime('now')
                    WHERE pattern_id = ?
                    """,
                    (
                        1 if vote == 1 else 0,
                        1 if vote == -1 else 0,
                        vote,
                        pattern_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO feedback_summary
                    (pattern_id, agent, issue_type, subsystem,
                     upvotes, downvotes, net_score, sample_text, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                    """,
                    (
                        pattern_id,
                        agent,
                        issue_type,
                        subsystem,
                        1 if vote == 1 else 0,
                        1 if vote == -1 else 0,
                        vote,
                        sample_text[:200],
                    ),
                )
            conn.commit()

    def get_relevant_feedback(self, query: str, agent: str, top_k: int = 5) -> list[dict[str, Any]]:
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=top_k,
                where={"agent": agent},
            )
            items: list[dict[str, Any]] = []
            for index, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][index]
                items.append(
                    {
                        "content": doc,
                        "vote": int(meta.get("vote", "0")),
                        "weight": float(meta.get("weight", "1.0")),
                        "issue_type": meta.get("issue_type", "general"),
                        "agent": meta.get("agent", agent),
                    }
                )
            return sorted(items, key=lambda item: item["weight"], reverse=True)
        except Exception:
            return []

    def build_feedback_context(self, query: str, agent: str) -> str:
        items = self.get_relevant_feedback(query, agent)
        if not items:
            return ""

        positive = [item for item in items if item["vote"] == 1]
        negative = [item for item in items if item["vote"] == -1]

        lines = ["Based on previous user feedback:"]
        for item in positive[:3]:
            lines.append(
                f"  PREFERRED: {item['content'][:100]}... (issue_type: {item['issue_type']})"
            )
        for item in negative[:2]:
            lines.append(
                f"  AVOID: {item['content'][:100]}... (issue_type: {item['issue_type']})"
            )
        return "\n".join(lines)

    def get_leaderboard(self, limit: int = 10) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT pattern_id, agent, issue_type, subsystem,
                       upvotes, downvotes, net_score, sample_text
                FROM feedback_summary
                ORDER BY net_score DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        keys = [
            "pattern_id",
            "agent",
            "issue_type",
            "subsystem",
            "upvotes",
            "downvotes",
            "net_score",
            "sample_text",
        ]
        return [dict(zip(keys, row)) for row in rows]
