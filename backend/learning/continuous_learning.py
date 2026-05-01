"""
Continuous learning engine for CHANAKYA and ARYABHATA.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Optional

import chromadb
from sentence_transformers import SentenceTransformer

SQLITE_PATH = os.getenv("SQLITE_PATH") or os.getenv("SQLITE_DB_PATH") or "/workspace/data/db/patchwise.db"
CHROMADB_PATH = os.getenv("CHROMADB_PATH", "/workspace/data/chromadb")
PROFILES_PATH = os.getenv("PROFILES_PATH", "/workspace/data/profiles")


class ContinuousLearning:
    def __init__(self) -> None:
        Path(CHROMADB_PATH).mkdir(parents=True, exist_ok=True)
        Path(PROFILES_PATH).mkdir(parents=True, exist_ok=True)
        self.chroma_client = chromadb.PersistentClient(path=CHROMADB_PATH)
        self._encoder: Optional[SentenceTransformer] = None

    @property
    def encoder(self) -> SentenceTransformer:
        if self._encoder is None:
            self._encoder = SentenceTransformer("all-MiniLM-L6-v2")
        return self._encoder

    def _connect(self) -> sqlite3.Connection:
        Path(SQLITE_PATH).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    async def store_review_pattern(self, session_id: str, issues: list[dict[str, Any]], subsystem: str) -> None:
        collection = self.chroma_client.get_or_create_collection("review_patterns")
        for issue in issues:
            doc_text = f"{issue.get('type')} {issue.get('description')} {issue.get('explanation')}"
            embedding = self.encoder.encode(doc_text).tolist()
            collection.add(
                ids=[f"{session_id}_{issue.get('id', '')}"],
                documents=[doc_text],
                embeddings=[embedding],
                metadatas=[
                    {
                        "session_id": session_id,
                        "subsystem": subsystem,
                        "issue_type": issue.get("type"),
                        "severity": issue.get("severity", "INFO"),
                        "line_number": str(issue.get("line_number", "")),
                    }
                ],
            )

    async def store_fix_pattern(
        self,
        session_id: str,
        fix_result: Any,
        issues: list[dict[str, Any]],
        subsystem: str,
    ) -> None:
        del issues
        if not getattr(fix_result, "validation_passed", False):
            return

        collection = self.chroma_client.get_or_create_collection("fix_patterns")
        with self._connect() as conn:
            for change in getattr(fix_result, "changes_made", []):
                doc_text = f"{change.get('issue_type')} fix: {change.get('original')} -> {change.get('fixed')}"
                embedding = self.encoder.encode(doc_text).tolist()
                collection.add(
                    ids=[f"{session_id}_{change.get('line', '')}_{change.get('issue_type', '')}"],
                    documents=[doc_text],
                    embeddings=[embedding],
                    metadatas=[{"subsystem": subsystem, "success": "true"}],
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO fix_patterns
                    (issue_type, issue_context, fix_applied, success_count, fail_count, subsystem)
                    VALUES (?, ?, ?, 1, 0, ?)
                    """,
                    (
                        change.get("issue_type"),
                        change.get("original"),
                        change.get("fixed"),
                        subsystem,
                    ),
                )
            conn.commit()

    async def apply_feedback(
        self,
        session_id: str,
        message_id: str,
        vote: str,
        feedback_text: Optional[str] = None,
    ) -> None:
        weight_delta = 1.0 if vote == "up" else -0.5

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO feedback_weights (session_id, message_id, vote, weight_delta, feedback_text)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, message_id, vote, weight_delta, feedback_text),
            )
            conn.commit()

        for collection_name in ["review_patterns", "fix_patterns"]:
            try:
                collection = self.chroma_client.get_collection(collection_name)
                existing = collection.get(ids=[message_id])
                if not existing.get("ids"):
                    continue
                metadata = existing["metadatas"][0]
                current_weight = float(metadata.get("weight", 1.0))
                metadata["weight"] = max(0.1, current_weight + weight_delta)
                collection.update(ids=[message_id], metadatas=[metadata])
            except Exception:
                continue

    async def update_subsystem_profile(self, subsystem: str, session_data: dict[str, Any]) -> None:
        profile_path = Path(PROFILES_PATH) / f"{subsystem}_profile.json"
        profile_path.parent.mkdir(parents=True, exist_ok=True)

        if profile_path.exists():
            profile = json.loads(profile_path.read_text())
        else:
            profile = {
                "subsystem": subsystem,
                "sessions_analyzed": 0,
                "chanakya_rules": {},
                "aryabhata_patterns": {},
                "maintainer_preferences": {},
                "common_issues": {},
                "successful_fix_patterns": {},
            }

        profile["sessions_analyzed"] += 1

        for issue in session_data.get("issues", []):
            key = f"{issue.get('type')}_{issue.get('line_number', 'N')}"
            profile["common_issues"][key] = profile["common_issues"].get(key, 0) + 1

        for comment in session_data.get("reviewer_comments", []):
            if comment.get("reviewer_type") != "MAINTAINER":
                continue
            email = comment.get("reviewer_email", "unknown")
            if email not in profile["maintainer_preferences"]:
                profile["maintainer_preferences"][email] = {
                    "name": comment.get("reviewer_name", ""),
                    "frequent_issues": {},
                    "total_reviews": 0,
                }
            profile["maintainer_preferences"][email]["total_reviews"] += 1
            phrase = comment.get("comment_text", "")[:200]
            freqs = profile["maintainer_preferences"][email]["frequent_issues"]
            freqs[phrase] = freqs.get(phrase, 0) + 1

        for fix in session_data.get("changes_made", []):
            issue_type = fix.get("issue_type", "UNKNOWN")
            profile["aryabhata_patterns"].setdefault(issue_type, [])
            if len(profile["aryabhata_patterns"][issue_type]) < 20:
                profile["aryabhata_patterns"][issue_type].append(
                    {
                        "original": fix.get("original", ""),
                        "fixed": fix.get("fixed", ""),
                        "reason": fix.get("reason", ""),
                    }
                )

        profile_path.write_text(json.dumps(profile, indent=2))

    async def get_relevant_context(self, patch_content: str, subsystem: str) -> dict[str, Any]:
        query_embedding = self.encoder.encode(patch_content[:500]).tolist()

        review_collection = self.chroma_client.get_or_create_collection("review_patterns")
        review_results = review_collection.query(
            query_embeddings=[query_embedding],
            n_results=5,
            where={"subsystem": subsystem},
        )

        fix_collection = self.chroma_client.get_or_create_collection("fix_patterns")
        fix_results = fix_collection.query(
            query_embeddings=[query_embedding],
            n_results=5,
            where={"subsystem": subsystem},
        )

        profile_path = Path(PROFILES_PATH) / f"{subsystem}_profile.json"
        profile: dict[str, Any] = {}
        if profile_path.exists():
            profile = json.loads(profile_path.read_text())

        return {
            "similar_review_patterns": review_results.get("documents", [[]])[0],
            "similar_fix_patterns": fix_results.get("documents", [[]])[0],
            "subsystem_profile": profile,
            "top_common_issues": sorted(
                profile.get("common_issues", {}).items(),
                key=lambda entry: entry[1],
                reverse=True,
            )[:5],
            "maintainer_preferences": profile.get("maintainer_preferences", {}),
        }
