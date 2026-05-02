from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class MessageType(str, Enum):
    CHALLENGE = "challenge"
    WITHDRAWAL = "withdrawal"
    CLARIFICATION_REQUEST = "clarification_request"
    CLARIFICATION_RESPONSE = "clarification_response"
    SURGICAL_LGTM = "surgical_lgtm"
    FULL_LGTM = "full_lgtm"
    ACCEPT = "accept"
    ESCALATE = "escalate"
    PROACTIVE_RISK_FLAG = "proactive_risk_flag"
    PRE_FIX_CONSULTATION = "pre_fix_consultation"
    PRE_FIX_RESPONSE = "pre_fix_response"
    COVER_LETTER_REQUEST = "cover_letter_request"
    COVER_LETTER_DRAFT = "cover_letter_draft"
    REVIEW_COVER_LETTER = "review_cover_letter"
    JOINT_CLARIFICATION = "joint_clarification"
    ARYABHATA_APPROVAL = "aryabhata_approval"


@dataclass
class BusMessage:
    session_id: str
    sender: str
    recipient: str
    message_type: MessageType
    content: dict[str, Any] = field(default_factory=dict)


class MessageBus:
    def __init__(self, challenge_timeout: int = 60):
        self.challenge_timeout = challenge_timeout
        self._queues: dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
        self._subscribers: dict[str, list[Callable[[BusMessage], Any]]] = defaultdict(list)

    def subscribe(self, key: str, callback: Callable[[BusMessage], Any]) -> None:
        self._subscribers[key].append(callback)

    async def publish(self, message: BusMessage) -> None:
        key = f"{message.session_id}:{message.recipient}"
        await self._queues[key].put(message)
        for callback in self._subscribers.get(key, []):
            result = callback(message)
            if asyncio.iscoroutine(result):
                await result

    async def receive(self, session_id: str, recipient: str, timeout: int | None = None) -> BusMessage | None:
        key = f"{session_id}:{recipient}"
        effective_timeout = timeout if timeout is not None else self.challenge_timeout
        try:
            return await asyncio.wait_for(self._queues[key].get(), timeout=effective_timeout)
        except asyncio.TimeoutError:
            return None

    async def wait_for_response(
        self,
        session_id: str,
        sender: str,
        message_type: MessageType,
        timeout: int = 60,
    ) -> dict[str, Any] | None:
        message = await self.receive(session_id, sender, timeout=timeout)
        if not message:
            return None
        if message.message_type != message_type:
            return None
        return message.content


message_bus = MessageBus(challenge_timeout=60)
