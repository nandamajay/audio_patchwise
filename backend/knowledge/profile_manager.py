"""
Knowledge profile export/import manager (.pkb format).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import chromadb

SQLITE_PATH = os.getenv("SQLITE_PATH") or os.getenv("SQLITE_DB_PATH") or "/workspace/data/db/patchwise.db"
CHROMADB_PATH = os.getenv("CHROMADB_PATH", "/workspace/data/chromadb")
PROFILES_PATH = os.getenv("PROFILES_PATH", "/workspace/data/profiles")


class KnowledgeProfileManager:
    def __init__(self) -> None:
        Path(CHROMADB_PATH).mkdir(parents=True, exist_ok=True)
        Path(PROFILES_PATH).mkdir(parents=True, exist_ok=True)
        self.chroma_client = chromadb.PersistentClient(path=CHROMADB_PATH)

    async def export_profile(self, export_config: dict[str, Any], password: Optional[str] = None) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        pkb_filename = f"patchwise_profile_{timestamp}.pkb"
        pkb_path = str(Path(PROFILES_PATH) / pkb_filename)

        selected = export_config.get("selected_components", [])
        subsystem = export_config.get("subsystem", "alsa-asoc")

        profile_data: dict[str, Any] = {
            "metadata": {
                "version": "1.0",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "subsystem": subsystem,
                "exported_by": export_config.get("user", "unknown"),
                "components": selected,
                "password_protected": password is not None,
            }
        }

        with zipfile.ZipFile(pkb_path, "w", zipfile.ZIP_DEFLATED) as zf:
            if "subsystem_rules" in selected:
                profile_data["subsystem_rules"] = self._export_subsystem_rules(subsystem)
            if "fix_patterns" in selected:
                profile_data["fix_patterns"] = self._export_fix_patterns()
            if "maintainer_prefs" in selected:
                profile_data["maintainer_prefs"] = self._export_maintainer_prefs()
            if "cover_letter_templates" in selected:
                profile_data["cover_letter_templates"] = self._export_cover_letter_templates()
            if "embeddings" in selected:
                profile_data["embeddings"] = self._export_embeddings(subsystem)
            if "lkml_cache" in selected:
                profile_data["lkml_cache"] = self._export_lkml_cache()

            profile_json = json.dumps(profile_data, indent=2)
            if password:
                encrypted = self._encrypt_content(profile_json, password)
                zf.writestr("profile.enc", encrypted)
                zf.writestr("profile.meta", json.dumps({"encrypted": True}))
                checksum_payload = encrypted
            else:
                zf.writestr("profile.json", profile_json)
                zf.writestr("profile.meta", json.dumps({"encrypted": False}))
                checksum_payload = profile_json

            checksum = hashlib.sha256(checksum_payload.encode()).hexdigest()
            zf.writestr("profile.sha256", checksum)

        return pkb_path

    async def import_profile(self, pkb_path: str, password: Optional[str] = None) -> dict[str, int]:
        results = {
            "rules_merged": 0,
            "patterns_merged": 0,
            "maintainer_prefs_merged": 0,
            "templates_added": 0,
            "embeddings_added": 0,
            "lkml_skipped_duplicates": 0,
            "lkml_added": 0,
        }

        with zipfile.ZipFile(pkb_path, "r") as zf:
            meta = json.loads(zf.read("profile.meta").decode())
            if meta.get("encrypted"):
                if not password:
                    raise ValueError("Profile is password protected - password required")
                encrypted = zf.read("profile.enc").decode()
                expected_checksum = zf.read("profile.sha256").decode()
                actual_checksum = hashlib.sha256(encrypted.encode()).hexdigest()
                if expected_checksum != actual_checksum:
                    raise ValueError("Profile integrity check failed")
                profile_json = self._decrypt_content(encrypted, password)
            else:
                profile_json = zf.read("profile.json").decode()
                expected_checksum = zf.read("profile.sha256").decode()
                actual_checksum = hashlib.sha256(profile_json.encode()).hexdigest()
                if expected_checksum != actual_checksum:
                    raise ValueError("Profile integrity check failed")

        profile_data = json.loads(profile_json)

        if "subsystem_rules" in profile_data:
            results["rules_merged"] = self._merge_subsystem_rules(profile_data["subsystem_rules"])
        if "fix_patterns" in profile_data:
            results["patterns_merged"] = self._merge_fix_patterns(profile_data["fix_patterns"])
        if "maintainer_prefs" in profile_data:
            results["maintainer_prefs_merged"] = self._merge_maintainer_prefs(profile_data["maintainer_prefs"])
        if "cover_letter_templates" in profile_data:
            results["templates_added"] = self._add_cover_letter_templates(profile_data["cover_letter_templates"])
        if "embeddings" in profile_data:
            results["embeddings_added"] = self._merge_embeddings(profile_data["embeddings"])
        if "lkml_cache" in profile_data:
            added, skipped = self._merge_lkml_cache(profile_data["lkml_cache"])
            results["lkml_added"] = added
            results["lkml_skipped_duplicates"] = skipped

        return results

    def _connect(self) -> sqlite3.Connection:
        Path(SQLITE_PATH).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _export_subsystem_rules(self, subsystem: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT rule_type, rule_content, confidence, source
                FROM subsystem_rules
                WHERE subsystem = ?
                """,
                (subsystem,),
            ).fetchall()
        return [{"type": r[0], "content": r[1], "confidence": r[2], "source": r[3]} for r in rows]

    def _export_fix_patterns(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT issue_type, issue_context, fix_applied, success_count, fail_count
                FROM fix_patterns
                WHERE success_count > 0
                """
            ).fetchall()
        return [
            {
                "issue_type": r[0],
                "context": r[1],
                "fix": r[2],
                "success_count": r[3],
                "fail_count": r[4],
            }
            for r in rows
        ]

    def _export_maintainer_prefs(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT maintainer_email, preference_type, preference_detail, confidence
                FROM maintainer_preferences
                """
            ).fetchall()
        return [{"email": r[0], "type": r[1], "detail": r[2], "confidence": r[3]} for r in rows]

    def _export_cover_letter_templates(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT subsystem, template_content, usage_count
                FROM cover_letter_templates
                """
            ).fetchall()
        return [{"subsystem": r[0], "content": r[1], "usage_count": r[2]} for r in rows]

    def _export_embeddings(self, subsystem: str) -> list[dict[str, Any]]:
        try:
            collection = self.chroma_client.get_collection("lkml_patches")
            results = collection.get(where={"subsystem": subsystem}, include=["documents", "metadatas"])
            ids = results.get("ids", [])
            docs = results.get("documents", [])
            metas = results.get("metadatas", [])
            exported: list[dict[str, Any]] = []
            for idx, doc_id in enumerate(ids):
                exported.append(
                    {
                        "id": doc_id,
                        "document": docs[idx] if idx < len(docs) else "",
                        "metadata": metas[idx] if idx < len(metas) else {},
                    }
                )
            return exported
        except Exception:
            return []

    def _export_lkml_cache(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT message_id, subject, author, date, subsystem, thread_url
                FROM lkml_cache
                """
            ).fetchall()
        return [
            {
                "message_id": row[0],
                "subject": row[1],
                "author": row[2],
                "date": row[3],
                "subsystem": row[4],
                "url": row[5],
            }
            for row in rows
        ]

    def _merge_subsystem_rules(self, rules: list[dict[str, Any]]) -> int:
        count = 0
        with self._connect() as conn:
            for rule in rules:
                existing = conn.execute(
                    "SELECT id FROM subsystem_rules WHERE rule_type = ? AND rule_content = ?",
                    (rule["type"], rule["content"]),
                ).fetchone()
                if existing:
                    continue
                conn.execute(
                    """
                    INSERT INTO subsystem_rules (rule_type, rule_content, confidence, source, subsystem)
                    VALUES (?, ?, ?, ?, 'alsa-asoc')
                    """,
                    (rule["type"], rule["content"], rule.get("confidence", 0.5), "imported"),
                )
                count += 1
            conn.commit()
        return count

    def _merge_fix_patterns(self, patterns: list[dict[str, Any]]) -> int:
        count = 0
        with self._connect() as conn:
            for pattern in patterns:
                existing = conn.execute(
                    "SELECT id FROM fix_patterns WHERE issue_type = ? AND fix_applied = ?",
                    (pattern["issue_type"], pattern["fix"]),
                ).fetchone()
                if existing:
                    conn.execute(
                        "UPDATE fix_patterns SET success_count = success_count + ? WHERE id = ?",
                        (pattern.get("success_count", 1), existing["id"]),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO fix_patterns
                        (issue_type, issue_context, fix_applied, success_count, fail_count)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            pattern["issue_type"],
                            pattern.get("context", ""),
                            pattern["fix"],
                            pattern.get("success_count", 1),
                            pattern.get("fail_count", 0),
                        ),
                    )
                    count += 1
            conn.commit()
        return count

    def _merge_maintainer_prefs(self, prefs: list[dict[str, Any]]) -> int:
        count = 0
        with self._connect() as conn:
            for pref in prefs:
                existing = conn.execute(
                    """
                    SELECT id
                    FROM maintainer_preferences
                    WHERE maintainer_email = ? AND preference_type = ?
                    """,
                    (pref["email"], pref["type"]),
                ).fetchone()
                if existing:
                    continue
                conn.execute(
                    """
                    INSERT INTO maintainer_preferences
                    (maintainer_email, preference_type, preference_detail, confidence)
                    VALUES (?, ?, ?, ?)
                    """,
                    (pref["email"], pref["type"], pref.get("detail"), pref.get("confidence", 0.5)),
                )
                count += 1
            conn.commit()
        return count

    def _add_cover_letter_templates(self, templates: list[dict[str, Any]]) -> int:
        count = 0
        with self._connect() as conn:
            for tmpl in templates:
                existing = conn.execute(
                    "SELECT id FROM cover_letter_templates WHERE subsystem = ?",
                    (tmpl["subsystem"],),
                ).fetchone()
                if existing:
                    continue
                conn.execute(
                    """
                    INSERT INTO cover_letter_templates (subsystem, template_content, usage_count)
                    VALUES (?, ?, 0)
                    """,
                    (tmpl["subsystem"], tmpl["content"]),
                )
                count += 1
            conn.commit()
        return count

    def _merge_lkml_cache(self, cache: list[dict[str, Any]]) -> tuple[int, int]:
        added = 0
        skipped = 0
        with self._connect() as conn:
            for entry in cache:
                existing = conn.execute(
                    "SELECT id FROM lkml_cache WHERE message_id = ?",
                    (entry["message_id"],),
                ).fetchone()
                if existing:
                    skipped += 1
                    continue
                conn.execute(
                    """
                    INSERT INTO lkml_cache (message_id, subject, author, date, subsystem, thread_url)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry["message_id"],
                        entry.get("subject"),
                        entry.get("author"),
                        entry.get("date"),
                        entry.get("subsystem"),
                        entry.get("url"),
                    ),
                )
                added += 1
            conn.commit()
        return added, skipped

    def _merge_embeddings(self, embeddings: list[dict[str, Any]]) -> int:
        if not embeddings:
            return 0
        try:
            collection = self.chroma_client.get_or_create_collection("lkml_patches")
            existing = collection.get()
            existing_ids = set(existing.get("ids", []))
            new_items = [item for item in embeddings if item.get("id") not in existing_ids]
            if not new_items:
                return 0
            collection.add(
                ids=[item["id"] for item in new_items],
                documents=[item.get("document", "") for item in new_items],
                metadatas=[item.get("metadata", {}) for item in new_items],
            )
            return len(new_items)
        except Exception:
            return 0

    def _encrypt_content(self, content: str, password: str) -> str:
        key = hashlib.sha256(password.encode()).digest()
        encrypted = bytes([byte ^ key[idx % len(key)] for idx, byte in enumerate(content.encode())])
        return base64.b64encode(encrypted).decode()

    def _decrypt_content(self, encrypted_b64: str, password: str) -> str:
        key = hashlib.sha256(password.encode()).digest()
        encrypted = base64.b64decode(encrypted_b64.encode())
        decrypted = bytes([byte ^ key[idx % len(key)] for idx, byte in enumerate(encrypted)])
        return decrypted.decode()
