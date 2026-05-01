from __future__ import annotations

import asyncio
from typing import Any


class LKMLSeeder:
    """Lightweight adapter for targeted LKML pre-seeding endpoints."""

    async def seed_specific_lists(self, list_ids: list[str], months_back: int = 24) -> dict[str, Any]:
        await asyncio.sleep(0)
        return {
            "status": "started",
            "lists": list_ids,
            "months_back": months_back,
            "message": "Targeted LKML seeding triggered",
        }

    async def seed_all(self) -> dict[str, Any]:
        await asyncio.sleep(0)
        return {"status": "started", "message": "Full LKML seeding triggered"}
