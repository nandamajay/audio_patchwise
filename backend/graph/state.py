from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any


fix_ready_event = asyncio.Event()


@dataclass
class RoundStateGuard:
    """
    round_guard helper to prevent duplicate/replayed round execution.
    """

    seen_round_ids: set[str] = field(default_factory=set)

    def should_skip(self, round_id: str) -> bool:
        if round_id in self.seen_round_ids:
            return True
        self.seen_round_ids.add(round_id)
        return False


@dataclass
class SharedA2AContext:
    session_id: str = ""
    shared_context: dict[str, Any] = field(default_factory=dict)
    a2a_state: dict[str, Any] = field(default_factory=dict)
    negotiation_threads: dict[str, Any] = field(default_factory=dict)
    challenge_timeout: int = 60
