"""
True A2A Negotiation Protocol
CHANAKYA and ARYABHATA communicate via typed messages.
Backend routes and broadcasts messages.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


class MessageType(Enum):
    # CHANAKYA -> ARYABHATA
    REVIEW_REPORT = "REVIEW_REPORT"
    CHALLENGE_RESPONSE = "CHALLENGE_RESPONSE"
    CHALLENGE_WITHDRAW = "CHALLENGE_WITHDRAW"
    CHALLENGE_UPHOLD = "CHALLENGE_UPHOLD"
    SURGICAL_LGTM = "SURGICAL_LGTM"
    FULL_LGTM = "FULL_LGTM"
    ESCALATE_TO_USER = "ESCALATE_TO_USER"

    # ARYABHATA -> CHANAKYA
    FIX_PROPOSAL = "FIX_PROPOSAL"
    CHALLENGE = "CHALLENGE"
    CLARIFICATION_REQUEST = "CLARIFICATION_REQUEST"
    FIX_COMPLETE = "FIX_COMPLETE"
    SURGICAL_REQUEST = "SURGICAL_REQUEST"

    # System
    USER_HINT = "USER_HINT"
    TIMEOUT = "TIMEOUT"


@dataclass
class Evidence:
    source: str
    content: str
    url: Optional[str] = None
    confidence: float = 0.0
    subsystem: str = "ASoC"


@dataclass
class A2AMessage:
    sender: str
    receiver: str
    message_type: MessageType
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    evidence: list[Evidence] = field(default_factory=list)
    issue_id: Optional[str] = None
    round_number: int = 0
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    message_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    confidence: Optional[float] = None


@dataclass
class NegotiationThread:
    issue_id: str
    issue_description: str
    messages: list[A2AMessage] = field(default_factory=list)
    resolved: bool = False
    resolution: str = ""
    challenge_count: int = 0
    timeout_seconds: int = 60


@dataclass
class SharedA2AContext:
    session_id: str
    original_patch: str
    current_patch: str
    round_number: int = 0
    negotiation_threads: Dict[str, NegotiationThread] = field(default_factory=dict)
    all_messages: list[A2AMessage] = field(default_factory=list)
    touched_lines: list[int] = field(default_factory=list)
    impact_radius: Dict[str, Any] = field(default_factory=dict)
    chanakya_knowledge: Dict[str, Any] = field(default_factory=dict)
    aryabhata_fix_result: Optional[Any] = None
    user_arbitration_pending: bool = False
    lgtm: bool = False
    challenge_timeout: int = 60


class A2AMessageBus:
    """
    Async pub/sub message bus for direct agent-to-agent communication.
    """

    def __init__(self):
        self._queues: Dict[str, asyncio.Queue] = {}
        self._timeout_tasks: Dict[str, asyncio.Task] = {}
        self._websocket_manager = None

    def set_websocket_manager(self, manager) -> None:
        self._websocket_manager = manager

    async def send(self, session_id: str, message: A2AMessage) -> None:
        queue_key = f"{session_id}:{message.receiver}"
        if queue_key not in self._queues:
            self._queues[queue_key] = asyncio.Queue()
        await self._queues[queue_key].put(message)

        if self._websocket_manager:
            payload = {
                "sender": message.sender,
                "receiver": message.receiver,
                "type": message.message_type.value,
                "content": message.content,
                "metadata": message.metadata,
                "issue_id": message.issue_id,
                "round": message.round_number,
                "confidence": message.confidence,
                "message_id": message.message_id,
                "timestamp": message.timestamp,
                "evidence": [e.__dict__ for e in message.evidence],
            }
            await self._websocket_manager.broadcast(
                session_id,
                {
                    "agent": "system",
                    "type": "a2a_message",
                    "round": message.round_number,
                    "content": message.content,
                    "metadata": payload,
                },
            )

    async def receive(
        self,
        session_id: str,
        receiver: str,
        timeout: int = 60,
    ) -> Optional[A2AMessage]:
        queue_key = f"{session_id}:{receiver}"
        if queue_key not in self._queues:
            self._queues[queue_key] = asyncio.Queue()

        try:
            return await asyncio.wait_for(self._queues[queue_key].get(), timeout=timeout)
        except asyncio.TimeoutError:
            return A2AMessage(
                sender="SYSTEM",
                receiver=receiver,
                message_type=MessageType.TIMEOUT,
                content=f"Challenge timeout ({timeout}s) — auto-proceeding",
                metadata={"timeout_seconds": timeout},
            )

    async def start_challenge_timeout(
        self,
        session_id: str,
        issue_id: str,
        timeout_seconds: int,
        on_timeout_callback,
    ) -> None:
        async def timeout_task():
            await asyncio.sleep(timeout_seconds)
            await on_timeout_callback(session_id, issue_id)

        task_key = f"{session_id}:{issue_id}"
        self.cancel_challenge_timeout(session_id, issue_id)
        self._timeout_tasks[task_key] = asyncio.create_task(timeout_task())

    def cancel_challenge_timeout(self, session_id: str, issue_id: str) -> None:
        task_key = f"{session_id}:{issue_id}"
        task = self._timeout_tasks.get(task_key)
        if not task:
            return
        task.cancel()
        del self._timeout_tasks[task_key]


message_bus = A2AMessageBus()
