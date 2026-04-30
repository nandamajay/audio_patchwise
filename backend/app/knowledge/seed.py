from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import requests
from bs4 import BeautifulSoup

from app.knowledge.sql_store import PatchSQLStore
from app.knowledge.vector_store import PatchVectorStore


@dataclass
class SeedItem:
    patch_id: str
    title: str
    author: str
    date: str
    subsystem: str
    verdict: str
    url: str
    content: str


def _extract_items(base_url: str, subsystem: str, months: int, limit: int = 30) -> list[SeedItem]:
    cutoff = datetime.now(UTC) - timedelta(days=30 * months)
    response = requests.get(base_url, timeout=20)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "lxml")
    anchors = soup.find_all("a", href=True)

    items: list[SeedItem] = []
    seen: set[str] = set()
    for anchor in anchors:
        href = anchor["href"]
        title = anchor.get_text(strip=True)
        if not title or "patch" not in title.lower():
            continue

        if href.startswith("/"):
            url = f"https://lore.kernel.org{href}"
        elif href.startswith("http"):
            url = href
        else:
            continue

        if url in seen:
            continue
        seen.add(url)

        # Extract a lightweight date hint from the URL if available.
        date_match = re.search(r"(20\d{2})(\d{2})(\d{2})", url)
        if date_match:
            year, month, day = map(int, date_match.groups())
            item_date = datetime(year, month, day, tzinfo=UTC)
        else:
            item_date = datetime.now(UTC)

        if item_date < cutoff:
            continue

        patch_id = f"lkml-{len(items) + 1:05d}"
        items.append(
            SeedItem(
                patch_id=patch_id,
                title=title[:180],
                author="alsa-devel",
                date=item_date.date().isoformat(),
                subsystem=subsystem,
                verdict="HISTORICAL",
                url=url,
                content=f"Thread: {title}\nURL: {url}",
            )
        )
        if len(items) >= limit:
            break

    return items


def run_seed(subsystem: str, months: int) -> dict:
    base_url = "https://lore.kernel.org/alsa-devel/"
    vector_store = PatchVectorStore(collection_name="patchwise_alsa_asoc")
    sql_store = PatchSQLStore()

    items = _extract_items(base_url=base_url, subsystem=subsystem, months=months)
    for item in items:
        vector_store.add_patch(
            {
                "patch_id": item.patch_id,
                "title": item.title,
                "author": item.author,
                "date": item.date,
                "subsystem": item.subsystem,
                "verdict": item.verdict,
                "url": item.url,
                "content": item.content,
            }
        )

    for item in items:
        sql_store.update_from_session(
            {
                "session_id": item.patch_id,
                "subsystem": item.subsystem,
                "current_round": 0,
                "verdict": item.verdict,
                "quality_score": 100.0,
                "review_findings": [],
                "fix_attempts": [],
                "similar_patches": [
                    {
                        "title": item.title,
                        "url": item.url,
                        "author": item.author,
                        "relevance_score": 1.0,
                    }
                ],
            }
        )

    return {
        "status": "ok",
        "subsystem": subsystem,
        "months": months,
        "seeded_count": len(items),
        "source": base_url,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed PatchWise LKML knowledge base")
    parser.add_argument("--subsystem", default="alsa-asoc")
    parser.add_argument("--months", type=int, default=24)
    args = parser.parse_args()

    result = run_seed(subsystem=args.subsystem, months=args.months)
    print(result)


if __name__ == "__main__":
    main()
