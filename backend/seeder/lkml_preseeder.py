"""
Incremental LKML sync for PatchWise.
"""
from __future__ import annotations

import logging
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from database import get_db_connection, get_write_connection
from knowledge.chroma_manager import queue_kb_write

logger = logging.getLogger(__name__)

LKML_AUDIO_LISTS = [
    "https://lore.kernel.org/alsa-devel/",
    "https://lore.kernel.org/linux-sound/",
    "https://lore.kernel.org/linux-audio-dev/",
]


async def get_last_seeded_date() -> datetime:
    """Return date of last successful seed run."""
    conn = get_db_connection()
    row = conn.execute(
        """
        SELECT run_at FROM seed_run_history
        WHERE status = 'success'
        ORDER BY run_at DESC LIMIT 1
        """
    ).fetchone()

    if row:
        parsed = datetime.fromisoformat(row["run_at"])
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    return datetime.now(timezone.utc) - timedelta(days=730)


async def run_incremental_seed() -> dict[str, Any]:
    """
    Fetch only patches newer than the last successful run.
    """
    since_date = await get_last_seeded_date()
    logger.info("[Seeder] Incremental sync from %s", since_date.isoformat())

    patches_fetched = 0
    embeddings_created = 0

    for list_url in LKML_AUDIO_LISTS:
        try:
            new_patches = await fetch_patches_since(list_url, since_date)
            for patch in new_patches:
                await store_patch_with_embedding(patch)
                patches_fetched += 1
                embeddings_created += 1
            logger.info("[Seeder] %s: %s new patches", list_url, len(new_patches))
        except Exception as exc:
            logger.warning("[Seeder] Failed to fetch %s: %s", list_url, exc)

    return {
        "patches_fetched": patches_fetched,
        "embeddings_created": embeddings_created,
        "lists_crawled": len(LKML_AUDIO_LISTS),
        "since_date": since_date.isoformat(),
    }


async def fetch_patches_since(list_url: str, since_date: datetime) -> list[dict[str, Any]]:
    """Fetch patches from lore.kernel.org newer than since_date."""
    async with httpx.AsyncClient(timeout=30) as client:
        feed_url = f"{list_url}?since={since_date.strftime('%Y%m%d')}&format=atom"
        response = await client.get(feed_url)
        response.raise_for_status()
        return parse_atom_feed(response.text, since_date)


def parse_atom_feed(feed_xml: str, since_date: datetime) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []

    try:
        root = ET.fromstring(feed_xml)
    except ET.ParseError:
        return entries

    namespaces = {
        "atom": "http://www.w3.org/2005/Atom",
    }

    for entry in root.findall("atom:entry", namespaces):
        updated_raw = _text(entry, "atom:updated", namespaces)
        updated_dt = _parse_feed_datetime(updated_raw)
        if updated_dt and updated_dt < since_date:
            continue

        link = ""
        link_node = entry.find("atom:link", namespaces)
        if link_node is not None:
            link = link_node.attrib.get("href", "")

        entries.append(
            {
                "title": _text(entry, "atom:title", namespaces),
                "id": _text(entry, "atom:id", namespaces),
                "updated": updated_raw,
                "author": _text(entry, "atom:author/atom:name", namespaces),
                "summary": _text(entry, "atom:summary", namespaces),
                "content": _text(entry, "atom:content", namespaces) or _text(entry, "atom:summary", namespaces),
                "url": link,
                "subsystem": "audio",
                "issue_type": "lkml_patch",
            }
        )

    return entries


def _text(node: ET.Element, path: str, namespaces: dict[str, str]) -> str:
    target = node.find(path, namespaces)
    if target is None or target.text is None:
        return ""
    return target.text.strip()


def _parse_feed_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


async def store_patch_with_embedding(patch: dict[str, Any]) -> None:
    """Persist patch metadata and queue Chroma embedding write."""
    now = datetime.now(timezone.utc).isoformat()
    with get_write_connection() as conn:
        conn.execute(
            """
            INSERT INTO knowledge_base
            (subsystem, issue_type, pattern, fix_pattern, source,
             upvotes, downvotes, confidence, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?, ?)
            """,
            (
                patch.get("subsystem", "audio"),
                patch.get("issue_type", "lkml_patch"),
                patch.get("title", ""),
                patch.get("summary", ""),
                patch.get("url", "lore.kernel.org"),
                0.5,
                now,
                now,
            ),
        )

    await queue_kb_write(
        collection="audio_patches",
        documents=[patch.get("content", "") or patch.get("summary", "")],
        metadatas=[
            {
                "title": patch.get("title", ""),
                "url": patch.get("url", ""),
                "updated": patch.get("updated", ""),
                "author": patch.get("author", ""),
                "source": "lkml",
            }
        ],
        ids=[patch.get("id") or str(uuid.uuid4())],
    )
