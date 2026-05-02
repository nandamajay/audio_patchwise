"""
Patch version intelligence for lore/kernel threads.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import email
import gzip
import json
import os
import re
import sqlite3
from typing import Optional

import httpx

SQLITE_PATH = os.getenv("SQLITE_PATH") or os.getenv("SQLITE_DB_PATH") or "/workspace/data/db/patchwise.db"

KEY_MAINTAINERS = {
    "tiwai@suse.de",
    "broonie@kernel.org",
    "perex@perex.cz",
    "lgirdwood@gmail.com",
    "plai@kernel.org",
    "bgoswami@quicinc.com",
}


@dataclass
class ReviewerComment:
    author: str
    email: str
    role: str
    body: str
    message_id: str
    in_reply_to: str = ""
    line_reference: Optional[str] = None
    suggested_reply: str = ""
    reply_quality: str = "MISSING"  # ADEQUATE | INCOMPLETE | MISSING


@dataclass
class VersionNode:
    version: int
    thread_url: str
    message_id: str = ""
    source: str = "subject_search"


@dataclass
class PatchVersionChain:
    current_version: int
    versions: list[VersionNode] = field(default_factory=list)
    reviewer_comments: list[ReviewerComment] = field(default_factory=list)
    addressed_comments: list[ReviewerComment] = field(default_factory=list)
    unaddressed_comments: list[ReviewerComment] = field(default_factory=list)
    previous_links: list[str] = field(default_factory=list)
    fetch_status: str = "NO_HISTORY"  # SUCCESS | DEGRADED | NO_HISTORY
    found_via: str = "not_found"  # user_link | patch_link | subject_search | cache | not_found


class PatchVersionIntelligence:
    def __init__(self, db_path: str = SQLITE_PATH) -> None:
        self.db_path = db_path
        self._ensure_cache_table()

    async def get_version_chain(
        self,
        patch_content: str,
        user_provided_link: str = "",
        session_id: str = "",
    ) -> PatchVersionChain:
        current_version = self._detect_version(patch_content)
        subject = self._extract_clean_subject(patch_content)
        cache_key = f"{subject}|v{current_version}"

        cached = self._load_cache(cache_key)
        if cached:
            cached.found_via = "cache"
            return cached

        if current_version <= 1:
            chain = PatchVersionChain(current_version=current_version, fetch_status="NO_HISTORY", found_via="not_found")
            self._save_cache(cache_key, chain)
            return chain

        link_candidates = self._collect_candidate_links(patch_content, user_provided_link)
        chain = PatchVersionChain(current_version=current_version, previous_links=link_candidates)

        # PRIORITY 1: user-provided link
        if user_provided_link and self._is_lore_link(user_provided_link):
            loaded = await self._load_chain_from_link(user_provided_link, current_version, patch_content, "user_link")
            if loaded:
                self._save_cache(cache_key, loaded)
                return loaded

        # PRIORITY 2: Link: headers and lore urls in body
        for link in link_candidates:
            loaded = await self._load_chain_from_link(link, current_version, patch_content, "patch_link")
            if loaded:
                self._save_cache(cache_key, loaded)
                return loaded

        # PRIORITY 3: subject search
        if subject and "*** SUBJECT HERE ***" not in subject:
            try:
                loaded = await self._load_chain_from_subject(subject, current_version, patch_content)
                if loaded:
                    self._save_cache(cache_key, loaded)
                    return loaded
            except Exception:
                pass

        # PRIORITY 4: soft degrade
        chain.fetch_status = "DEGRADED"
        chain.found_via = "not_found"
        self._save_cache(cache_key, chain)
        return chain

    def _detect_version(self, patch_content: str) -> int:
        match = re.search(r"\[PATCH\s+v(\d+)", patch_content, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return 1

    def _extract_clean_subject(self, patch_content: str) -> str:
        match = re.search(r"^Subject:\s*(.+)$", patch_content, re.MULTILINE)
        if not match:
            return ""
        subject = match.group(1).strip()
        subject = re.sub(r"\[PATCH[^\]]*\]\s*", "", subject).strip()
        return subject

    def _collect_candidate_links(self, patch_content: str, user_link: str) -> list[str]:
        links: list[str] = []
        if user_link and self._is_lore_link(user_link):
            links.append(user_link.strip())

        for match in re.findall(r"^Link:\s*(https?://[^\s]+)", patch_content, flags=re.MULTILINE):
            if self._is_lore_link(match):
                links.append(match.strip())

        for match in re.findall(r"https?://lore\.kernel\.org/[^\s>]+", patch_content):
            links.append(match.strip())

        deduped: list[str] = []
        seen: set[str] = set()
        for item in links:
            key = item.rstrip("/")
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _is_lore_link(self, value: str) -> bool:
        v = (value or "").strip().lower()
        return "lore.kernel.org" in v or "lkml.org" in v

    async def _load_chain_from_link(
        self,
        link: str,
        current_version: int,
        current_patch: str,
        found_via: str,
    ) -> Optional[PatchVersionChain]:
        try:
            chain = await self._build_chain(link, current_version, current_patch, found_via)
            if chain.versions:
                return chain
            return None
        except Exception:
            return None

    async def _load_chain_from_subject(
        self,
        subject: str,
        current_version: int,
        current_patch: str,
    ) -> Optional[PatchVersionChain]:
        versions: list[VersionNode] = []
        for version in range(1, current_version):
            url = await self._search_lore_subject(subject, version)
            if not url:
                continue
            versions.append(VersionNode(version=version, thread_url=url, source="subject_search"))

        if not versions:
            return None

        chain = PatchVersionChain(
            current_version=current_version,
            versions=versions,
            fetch_status="SUCCESS",
            found_via="subject_search",
        )
        all_comments: list[ReviewerComment] = []
        for node in chain.versions:
            comments, msg_id = await self._fetch_version_comments(node.thread_url)
            node.message_id = msg_id
            all_comments.extend(comments)

        addressed, unaddressed = self._classify_comments(all_comments, current_patch)
        chain.reviewer_comments = all_comments
        chain.addressed_comments = addressed
        chain.unaddressed_comments = unaddressed
        if not all_comments:
            chain.fetch_status = "DEGRADED"
        return chain

    async def _build_chain(
        self,
        start_link: str,
        current_version: int,
        current_patch: str,
        found_via: str,
    ) -> PatchVersionChain:
        chain = PatchVersionChain(
            current_version=current_version,
            fetch_status="SUCCESS",
            found_via=found_via,
        )

        # Best-effort infer start version from link/subject text
        inferred_prev = max(1, current_version - 1)
        chain.versions.append(VersionNode(version=inferred_prev, thread_url=start_link, source=found_via))

        all_comments: list[ReviewerComment] = []
        for node in list(chain.versions):
            comments, msg_id = await self._fetch_version_comments(node.thread_url)
            node.message_id = msg_id
            all_comments.extend(comments)

        # Fill missing older versions via subject search extracted from current patch
        subject = self._extract_clean_subject(current_patch)
        if subject and "*** SUBJECT HERE ***" not in subject:
            for version in range(1, inferred_prev):
                if any(v.version == version for v in chain.versions):
                    continue
                url = await self._search_lore_subject(subject, version)
                if not url:
                    continue
                vnode = VersionNode(version=version, thread_url=url, source="subject_search")
                comments, msg_id = await self._fetch_version_comments(url)
                vnode.message_id = msg_id
                chain.versions.append(vnode)
                all_comments.extend(comments)

        chain.versions.sort(key=lambda item: item.version)
        addressed, unaddressed = self._classify_comments(all_comments, current_patch)
        chain.reviewer_comments = all_comments
        chain.addressed_comments = addressed
        chain.unaddressed_comments = unaddressed
        if not chain.versions:
            chain.fetch_status = "NO_HISTORY"
        elif not all_comments:
            chain.fetch_status = "DEGRADED"
        return chain

    async def _search_lore_subject(self, subject: str, version: int) -> Optional[str]:
        query = re.sub(r"\s+", "+", f"{subject} v{version}").strip("+")
        if not query:
            return None
        url = f"https://lore.kernel.org/alsa-devel/?q={query}"
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            match = re.search(r'href="(https://lore\.kernel\.org/[^"#?]+)"', resp.text)
            if not match:
                return None
            return match.group(1)

    async def _fetch_version_comments(self, thread_url: str) -> tuple[list[ReviewerComment], str]:
        candidates = [
            f"{thread_url.rstrip('/')}/mbox.gz",
            f"{thread_url.rstrip('/')}/raw",
        ]
        for candidate in candidates:
            try:
                async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                    resp = await client.get(candidate)
                    if resp.status_code != 200:
                        continue
                    body = resp.content
                    if candidate.endswith(".gz"):
                        body = gzip.decompress(body)
                    text = body.decode("utf-8", errors="replace")
                    comments, message_id = self._parse_mbox(text)
                    return comments, message_id
            except Exception:
                continue
        return [], ""

    def _parse_mbox(self, mbox_text: str) -> tuple[list[ReviewerComment], str]:
        parser = email.parser.Parser()
        chunks = re.split(r"^From ", mbox_text, flags=re.MULTILINE)
        comments: list[ReviewerComment] = []
        root_message_id = ""
        for idx, chunk in enumerate(chunks[1:], start=1):
            raw = "From " + chunk
            try:
                msg = parser.parsestr(raw)
            except Exception:
                continue

            from_header = msg.get("From", "")
            author, email_addr = self._parse_from(from_header)
            role = self._classify_role(email_addr)
            body = self._extract_plain_text(msg)
            if not body.strip():
                continue

            message_id = (msg.get("Message-Id", "") or "").strip("<>")
            if idx == 1:
                root_message_id = message_id

            comment = ReviewerComment(
                author=author,
                email=email_addr,
                role=role,
                body=body[:2500],
                message_id=message_id,
                in_reply_to=(msg.get("In-Reply-To", "") or "").strip("<>"),
                line_reference=self._extract_line_reference(body),
            )
            comment.suggested_reply = self._generate_ack_reply(comment)
            comments.append(comment)

        return comments, root_message_id

    def _parse_from(self, header: str) -> tuple[str, str]:
        match = re.match(r"(.+?)\s*<([^>]+)>", header or "")
        if not match:
            text = (header or "").strip()
            return text, text.lower()
        return match.group(1).strip().strip('"'), match.group(2).strip().lower()

    def _classify_role(self, email_addr: str) -> str:
        mail = (email_addr or "").lower()
        if mail in KEY_MAINTAINERS:
            return "MAINTAINER"
        if "kernel.org" in mail or "linux" in mail:
            return "CONTRIBUTOR"
        return "COMMUNITY"

    def _extract_plain_text(self, msg) -> str:
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() != "text/plain":
                    continue
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
                return payload.decode("utf-8", errors="replace")
            return ""
        payload = msg.get_payload(decode=True)
        if payload is None:
            return str(msg.get_payload() or "")
        return payload.decode("utf-8", errors="replace")

    def _extract_line_reference(self, body: str) -> Optional[str]:
        match = re.search(r"line\s+(\d+)", body, flags=re.IGNORECASE)
        if not match:
            return None
        return f"line {match.group(1)}"

    def _classify_comments(
        self,
        comments: list[ReviewerComment],
        current_patch: str,
    ) -> tuple[list[ReviewerComment], list[ReviewerComment]]:
        addressed: list[ReviewerComment] = []
        unaddressed: list[ReviewerComment] = []
        patch_lower = (current_patch or "").lower()
        for comment in comments:
            key_terms = self._extract_key_terms(comment.body)
            matches = sum(1 for term in key_terms if term in patch_lower)
            if matches >= 2:
                comment.reply_quality = "ADEQUATE"
                addressed.append(comment)
            elif matches == 1:
                comment.reply_quality = "INCOMPLETE"
                unaddressed.append(comment)
            else:
                comment.reply_quality = "MISSING"
                unaddressed.append(comment)
        return addressed, unaddressed

    def _extract_key_terms(self, text: str) -> list[str]:
        cleaned = " ".join(
            line for line in (text or "").splitlines() if not line.strip().startswith(">")
        )
        words = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_\-]{3,}\b", cleaned.lower())
        unique: list[str] = []
        for word in words:
            if word in unique:
                continue
            unique.append(word)
            if len(unique) >= 8:
                break
        return unique

    def _generate_ack_reply(self, comment: ReviewerComment) -> str:
        if comment.role == "MAINTAINER":
            return "ACK: thanks, addressed in this revision."
        if comment.role == "CONTRIBUTOR":
            return "ACK: fixed per review feedback."
        return "ACK: thanks, incorporated in vN."

    def _ensure_cache_table(self) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS version_chain_cache (
                        cache_key TEXT PRIMARY KEY,
                        payload TEXT NOT NULL,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.commit()
        except Exception:
            pass

    def _save_cache(self, cache_key: str, chain: PatchVersionChain) -> None:
        payload = {
            "current_version": chain.current_version,
            "versions": [asdict(item) for item in chain.versions],
            "reviewer_comments": [asdict(item) for item in chain.reviewer_comments],
            "addressed_comments": [asdict(item) for item in chain.addressed_comments],
            "unaddressed_comments": [asdict(item) for item in chain.unaddressed_comments],
            "previous_links": chain.previous_links,
            "fetch_status": chain.fetch_status,
            "found_via": chain.found_via,
        }
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO version_chain_cache(cache_key, payload, updated_at)
                    VALUES(?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(cache_key) DO UPDATE SET
                        payload=excluded.payload,
                        updated_at=CURRENT_TIMESTAMP
                    """,
                    (cache_key, json.dumps(payload, ensure_ascii=False)),
                )
                conn.commit()
        except Exception:
            pass

    def _load_cache(self, cache_key: str) -> Optional[PatchVersionChain]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    "SELECT payload FROM version_chain_cache WHERE cache_key = ?",
                    (cache_key,),
                ).fetchone()
            if not row:
                return None
            data = json.loads(row[0])
            chain = PatchVersionChain(
                current_version=int(data.get("current_version", 1)),
                versions=[VersionNode(**item) for item in data.get("versions", [])],
                reviewer_comments=[ReviewerComment(**item) for item in data.get("reviewer_comments", [])],
                addressed_comments=[ReviewerComment(**item) for item in data.get("addressed_comments", [])],
                unaddressed_comments=[ReviewerComment(**item) for item in data.get("unaddressed_comments", [])],
                previous_links=list(data.get("previous_links", [])),
                fetch_status=str(data.get("fetch_status", "NO_HISTORY")),
                found_via=str(data.get("found_via", "cache")),
            )
            return chain
        except Exception:
            return None
