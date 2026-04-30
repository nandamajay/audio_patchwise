from __future__ import annotations

import asyncio
from enum import Enum
from typing import Optional


class InterruptSignal(str, Enum):
    PAUSE = "pause"
    RESUME = "resume"
    ABORT = "abort"


class InterruptHandler:
    """Manages per-session interrupt signals for pause/resume/abort."""

    def __init__(self) -> None:
        self._signals: dict[str, asyncio.Event] = {}
        self._hints: dict[str, Optional[str]] = {}
        self._status: dict[str, InterruptSignal] = {}

    def register_session(self, session_id: str) -> None:
        self._signals[session_id] = asyncio.Event()
        self._hints[session_id] = None
        self._status[session_id] = InterruptSignal.RESUME

    def send_interrupt(self, session_id: str, hint: Optional[str] = None) -> None:
        self._hints[session_id] = hint
        self._status[session_id] = InterruptSignal.PAUSE
        self._signals.setdefault(session_id, asyncio.Event()).set()

    def send_resume(self, session_id: str) -> None:
        self._status[session_id] = InterruptSignal.RESUME
        self._signals.setdefault(session_id, asyncio.Event()).clear()

    def send_abort(self, session_id: str) -> None:
        self._status[session_id] = InterruptSignal.ABORT
        self._signals.setdefault(session_id, asyncio.Event()).set()

    async def wait_for_resume(self, session_id: str) -> Optional[str]:
        if self._signals.setdefault(session_id, asyncio.Event()).is_set():
            hint = self._hints.get(session_id)
            self._hints[session_id] = None
            return hint
        return None

    def is_interrupted(self, session_id: str) -> bool:
        return self._status.get(session_id) == InterruptSignal.PAUSE

    def is_aborted(self, session_id: str) -> bool:
        return self._status.get(session_id) == InterruptSignal.ABORT

    def get_hint(self, session_id: str) -> Optional[str]:
        return self._hints.get(session_id)


interrupt_handler = InterruptHandler()
