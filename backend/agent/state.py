from __future__ import annotations

from typing import Any, TypedDict


class PatchWiseState(TypedDict, total=False):
    session_id: str
    next: str
    verdict: str
    round: int
    max_rounds: int
    payload: dict[str, Any]
