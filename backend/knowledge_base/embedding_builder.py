from __future__ import annotations

import asyncio


async def rebuild_all() -> dict:
    """Rebuild embedding collections placeholder task."""
    await asyncio.sleep(0)
    return {"status": "started", "message": "Embedding rebuild triggered"}
