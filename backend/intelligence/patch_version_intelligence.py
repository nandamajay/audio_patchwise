"""
Patch version intelligence for lore.kernel.org threads.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import email
import json
import os
import re
import sqlite3
from typing import Any, Optional

import httpx

SQLITE_PATH = os.getenv("SQLITE_PATH") or os.getenv("SQLITE_DB_PATH") or "/workspace/data/db/patchwise.db"


@dataclass
class ReviewerComment:
    reviewer_name: str
    reviewer_email: str
    reviewer_type: str
    comment_text: str
    in_reply_to: Optional[str]
    message_id: str
    date: str
    line_reference: Optional[str]
    addressed_in_version: Optional[str] = None
    reply_quality: Optional[str] = None


@dataclass
class PatchVersionChain:
    latest_version: int
    versions: dict[int, dict[str, Any]]
    all_reviewer_comments: list[ReviewerComment]
    unaddressed_comments: list[ReviewerComment]
    addressed_comments: list[ReviewerComment]
    maintainers: list[str]


KNOWN_MAINTAINERS = {
    "tiwai@suse.de",
    "broonie@kernel.org",
    "perex@perex.cz",
    "alsa-devel@alsa-project.org",
    "lgirdwood@gmail.com",
    "plai@cs.ubc.ca",
    "bhumirks@gmail.com",
}


class PatchVersionIntelligence:
    def __init__(self) -> None:
        self.session_cache: dict[str, PatchVersionChain] = {}

    async def analyze_patch_version(
        self,
        patch_content: str,
        session_id: str,
    ) -> Optional[PatchVersionChain]:
        if session_id in self.session_cache:
            return self.session_cache[session_id]

        cached = self._load_from_cache(session_id)
        if cached:
            self.session_cache[session_id] = cached
            return cached

        version = self._detect_version(patch_content)
        if version <= 1:
            return None

        subject = self._extract_subject(patch_content)
        prev_link = self._extract_prev_link(patch_content)
        if not prev_link:
            prev_link = await self._search_lore_by_subject(subject, version - 1)
        if not prev_link:
            return None

        chain = await self._fetch_full_chain(prev_link, version, subject, patch_content)
        self.session_cache[session_id] = chain
        self._save_to_cache(session_id, chain)
        return chain

    def _detect_version(self, patch_content: str) -> int:
        match = re.search(r"\[PATCH\s+v(\d+)", patch_content, re.IGNORECASE)
        return int(match.group(1)) if match else 1

    def _extract_prev_link(self, patch_content: str) -> Optional[str]:
        match = re.search(r"Link:\s*(https?://[^\s\n]+)", patch_content)
        return match.group(1) if match else None

    def _extract_subject(self, patch_content: str) -> str:
        match = re.search(r"Subject:.*?\[PATCH[^\]]*\]\s*(.*)", patch_content)
        return match.group(1).strip() if match else ""

    async def _search_lore_by_subject(self, subject: str, version: int) -> Optional[str]:
        if not subject:
            return None
        query = f"{subject} v{version}"
        search_url = f"https://lore.kernel.org/alsa-devel/?q={query}&x=m"
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(search_url)
                if resp.status_code != 200:
                    return None
                match = re.search(r'href="(https://lore\.kernel\.org/[^"]+)"', resp.text)
                return match.group(1) if match else None
        except Exception:
            return None

    async def _fetch_full_chain(
        self,
        start_url: str,
        latest_version: int,
        subject: str,
        current_patch: str,
    ) -> PatchVersionChain:
        versions: dict[int, dict[str, Any]] = {}
        all_comments: list[ReviewerComment] = []

        # Bootstrap from provided previous-link.
        first_comments, first_msgid = await self._fetch_version_comments(start_url)
        if first_comments:
            inferred = latest_version - 1
            versions[inferred] = {"url": start_url, "comments": first_comments, "message_id": first_msgid}
            all_comments.extend(first_comments)

        # Best-effort lookup for older versions.
        for version in range(1, latest_version):
            if version in versions:
                continue
            version_url = await self._search_lore_by_subject(subject, version)
            if not version_url:
                continue
            comments, msgid = await self._fetch_version_comments(version_url)
            versions[version] = {"url": version_url, "comments": comments, "message_id": msgid}
            all_comments.extend(comments)

        addressed, unaddressed = self._classify_comments(all_comments, current_patch)
        maintainers = sorted({c.reviewer_email for c in all_comments if c.reviewer_email in KNOWN_MAINTAINERS})

        return PatchVersionChain(
            latest_version=latest_version,
            versions=versions,
            all_reviewer_comments=all_comments,
            unaddressed_comments=unaddressed,
            addressed_comments=addressed,
            maintainers=maintainers,
        )

    async def _fetch_version_comments(self, url: str) -> tuple[list[ReviewerComment], str]:
        raw_url = f"{url.rstrip('/')}/raw"
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(raw_url)
                if resp.status_code != 200:
                    return [], ""
                mbox_content = resp.text
                comments = self._parse_mbox_comments(mbox_content)
                return comments, self._extract_message_id(mbox_content)
        except Exception:
            return [], ""

    def _parse_mbox_comments(self, mbox_content: str) -> list[ReviewerComment]:
        comments: list[ReviewerComment] = []
        parser = email.parser.Parser()
        messages = re.split(r"^From ", mbox_content, flags=re.MULTILINE)

        for msg_str in messages[1:]:
            try:
                msg = parser.parsestr("From " + msg_str)
                from_header = msg.get("From", "")
                name_match = re.match(r"(.+?)\s*<(.+?)>", from_header)
                if name_match:
                    name = name_match.group(1).strip().strip('"')
                    email_addr = name_match.group(2).strip().lower()
                else:
                    name = from_header.strip()
                    email_addr = from_header.strip().lower()

                if email_addr in KNOWN_MAINTAINERS:
                    reviewer_type = "MAINTAINER"
                elif "@kernel.org" in email_addr or "@linux" in email_addr:
                    reviewer_type = "CONTRIBUTOR"
                else:
                    reviewer_type = "COMMUNITY"

                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            payload = part.get_payload(decode=True)
                            if payload:
                                body = payload.decode("utf-8", errors="replace")
                                break
                else:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        body = payload.decode("utf-8", errors="replace")

                if not body or len(body.strip()) < 10:
                    continue
                if body.strip().startswith("diff --git"):
                    continue

                comments.append(
                    ReviewerComment(
                        reviewer_name=name,
                        reviewer_email=email_addr,
                        reviewer_type=reviewer_type,
                        comment_text=body[:1000],
                        in_reply_to=msg.get("In-Reply-To", ""),
                        message_id=msg.get("Message-Id", ""),
                        date=msg.get("Date", ""),
                        line_reference=self._extract_line_reference(body),
                    )
                )
            except Exception:
                continue
        return comments

    def _extract_line_reference(self, body: str) -> Optional[str]:
        match = re.search(r"line\s+(\d+)", body, re.IGNORECASE)
        return f"line {match.group(1)}" if match else None

    def _extract_message_id(self, content: str) -> str:
        match = re.search(r"Message-Id:\s*<([^>]+)>", content, re.IGNORECASE)
        return match.group(1) if match else ""

    def _classify_comments(
        self,
        comments: list[ReviewerComment],
        current_patch: str,
    ) -> tuple[list[ReviewerComment], list[ReviewerComment]]:
        addressed: list[ReviewerComment] = []
        unaddressed: list[ReviewerComment] = []
        patch_lower = current_patch.lower()

        for comment in comments:
            key_phrases = self._extract_key_phrases(comment.comment_text)
            matched = any(phrase.lower() in patch_lower for phrase in key_phrases)
            if matched:
                comment.addressed_in_version = "current"
                comment.reply_quality = "ADEQUATE"
                addressed.append(comment)
            else:
                comment.reply_quality = "UNANSWERED"
                unaddressed.append(comment)
        return addressed, unaddressed

    def _extract_key_phrases(self, comment: str) -> list[str]:
        lines = [line for line in comment.splitlines() if not line.strip().startswith(">")]
        clean = " ".join(lines)
        phrases = re.findall(r"\b[a-z][a-z0-9_]{2,}\b|\b[A-Z][a-zA-Z]{2,}\b", clean)
        unique: list[str] = []
        for phrase in phrases:
            if phrase not in unique:
                unique.append(phrase)
            if len(unique) >= 10:
                break
        return unique

    def generate_suggested_reply(self, comment: ReviewerComment, fix_applied: bool) -> str:
        if fix_applied:
            return "Thanks for the review. Fixed in next version."
        if comment.reviewer_type == "MAINTAINER":
            return "Acknowledged. Will address in next version."
        return "Thanks for the feedback. Will fix in next version."

    def _load_from_cache(self, session_id: str) -> Optional[PatchVersionChain]:
        try:
            with sqlite3.connect(SQLITE_PATH) as conn:
                row = conn.execute(
                    "SELECT chain_data FROM patch_version_cache WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
            if not row:
                return None
            payload = json.loads(row[0])
            return self._chain_from_json(payload)
        except Exception:
            return None

    def _save_to_cache(self, session_id: str, chain: PatchVersionChain) -> None:
        try:
            with sqlite3.connect(SQLITE_PATH) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS patch_version_cache (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL UNIQUE,
                        chain_data TEXT NOT NULL,
                        cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT OR REPLACE INTO patch_version_cache (session_id, chain_data, cached_at)
                    VALUES (?, ?, datetime('now'))
                    """,
                    (session_id, json.dumps(self._chain_to_json(chain))),
                )
                conn.commit()
        except Exception:
            return

    def _chain_to_json(self, chain: PatchVersionChain) -> dict[str, Any]:
        return {
            "latest_version": chain.latest_version,
            "versions": {str(k): v for k, v in chain.versions.items()},
            "all_reviewer_comments": [asdict(c) for c in chain.all_reviewer_comments],
            "unaddressed_comments": [asdict(c) for c in chain.unaddressed_comments],
            "addressed_comments": [asdict(c) for c in chain.addressed_comments],
            "maintainers": chain.maintainers,
        }

    def _chain_from_json(self, payload: dict[str, Any]) -> PatchVersionChain:
        all_comments = [ReviewerComment(**item) for item in payload.get("all_reviewer_comments", [])]
        unaddressed = [ReviewerComment(**item) for item in payload.get("unaddressed_comments", [])]
        addressed = [ReviewerComment(**item) for item in payload.get("addressed_comments", [])]
        versions = {int(k): v for k, v in payload.get("versions", {}).items()}
        return PatchVersionChain(
            latest_version=int(payload.get("latest_version", 1)),
            versions=versions,
            all_reviewer_comments=all_comments,
            unaddressed_comments=unaddressed,
            addressed_comments=addressed,
            maintainers=list(payload.get("maintainers", [])),
        )
