from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class MessageType(str, Enum):
    CHALLENGE = "challenge"
    RESPONSE = "response"
    WITHDRAWAL = "withdrawal"
    CLARIFICATION_REQUEST = "clarification_request"
    CLARIFICATION_RESPONSE = "clarification_response"
    APPROVE = "approve"
    ESCALATE = "escalate"
    INTERNAL_QUERY = "internal_query"
    INTERNAL_ANSWER = "internal_answer"
    STATUS = "status"
    FINDING = "finding"
    FIX = "fix"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _infer_type(raw_type: str) -> MessageType:
    lowered = (raw_type or "").lower()
    if "challenge" in lowered:
        return MessageType.CHALLENGE
    if "clarification_request" in lowered:
        return MessageType.CLARIFICATION_REQUEST
    if "clarification_response" in lowered:
        return MessageType.CLARIFICATION_RESPONSE
    if "withdraw" in lowered:
        return MessageType.WITHDRAWAL
    if "approval" in lowered or lowered in {"lgtm", "approve"}:
        return MessageType.APPROVE
    if lowered in {"fix_complete", "patch", "fixed_patch"}:
        return MessageType.FIX
    if lowered in {"finding", "issue"}:
        return MessageType.FINDING
    if lowered in {"thinking", "status", "info", "analysis_source"}:
        return MessageType.STATUS
    return MessageType.RESPONSE


@dataclass
class A2AEnvelope:
    session_id: str
    round_num: int
    sender: str
    receiver: str
    message_type: MessageType
    content: str
    evidence: dict[str, Any] = field(default_factory=dict)
    confidence_score: float = 0.0
    source: str = "unknown"
    task_type: str = "analysis"
    issue_id: str | None = None
    timestamp: str = field(default_factory=_now)

    @classmethod
    def from_agent_payload(cls, session_id: str, payload: dict[str, Any]) -> "A2AEnvelope":
        sender = str(payload.get("agent", "system"))
        receiver = "aryabhata" if sender == "chanakya" else ("chanakya" if sender == "aryabhata" else "system")
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        message_type = _infer_type(str(payload.get("type", "")))
        confidence = metadata.get("confidence", 0.0)
        try:
            confidence_score = float(confidence or 0.0)
        except Exception:
            confidence_score = 0.0
        return cls(
            session_id=session_id,
            round_num=int(payload.get("round", 0) or 0),
            sender=sender,
            receiver=receiver,
            message_type=message_type,
            content=str(payload.get("content", "") or ""),
            evidence={
                "metadata": metadata,
                "raw_type": payload.get("type"),
            },
            confidence_score=confidence_score,
            source=str(payload.get("source") or metadata.get("source") or "unknown"),
            task_type=str(payload.get("task_type") or metadata.get("task_type") or "analysis"),
            issue_id=metadata.get("issue_id"),
            timestamp=_now(),
        )

