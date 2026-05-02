from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MessageType(str, Enum):
    CHALLENGE = "CHALLENGE"
    WITHDRAWAL = "WITHDRAWAL"
    CLARIFICATION = "CLARIFICATION"
    SURGICAL_LGTM = "SURGICAL_LGTM"
    FULL_LGTM = "FULL_LGTM"
    ACCEPT = "ACCEPT"
    ESCALATE = "ESCALATE"


@dataclass
class EvidenceEnvelope:
    lkml_refs: list[dict[str, Any]] = field(default_factory=list)
    kb_patterns: list[dict[str, Any]] = field(default_factory=list)
    checkpatch_output: str = ""
    lsp_context: dict[str, Any] = field(default_factory=dict)
    kernel_docs: list[str] = field(default_factory=list)


@dataclass
class A2AMessage:
    session_id: str
    round_num: int
    sender: str
    receiver: str
    message_type: MessageType
    content: dict[str, Any] = field(default_factory=dict)
    evidence: EvidenceEnvelope = field(default_factory=EvidenceEnvelope)
    confidence_score: float = 0.0
    issue_id: str | None = None


@dataclass
class NegotiationThread:
    session_id: str
    issue_id: str
    challenge_msg: A2AMessage | None = None
    response_msg: A2AMessage | None = None
    resolution: str = "pending"
    withdrawn: bool = False
