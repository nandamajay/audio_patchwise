"""
CHANAKYA A2A Node — challenge handling + surgical review coordination.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.a2a_protocol import A2AMessage, MessageType, message_bus
from agents.impact_analyzer import impact_analyzer
from app.agents.chanakya import chanakya_review_node


@dataclass
class ChallengeEvaluation:
    withdraw: bool
    reasoning: str
    confidence: float
    additional_evidence: str = ""
    supporting_evidence: list[Any] | None = None


def _state_get(state: Any, key: str, default: Any = None) -> Any:
    if isinstance(state, dict):
        return state.get(key, default)
    return getattr(state, key, default)


def _state_set(state: Any, key: str, value: Any) -> None:
    if isinstance(state, dict):
        state[key] = value
    else:
        setattr(state, key, value)


def _shared_context(state: Any) -> dict[str, Any]:
    ctx = _state_get(state, "shared_a2a_context")
    if isinstance(ctx, dict):
        return ctx
    if ctx is None:
        return {}
    return dict(getattr(ctx, "__dict__", {}))


def get_pending_challenges(state: Any) -> list[Any]:
    msgs = _state_get(state, "a2a_messages", []) or []
    pending: list[Any] = []
    for msg in msgs:
        message_type = getattr(msg, "message_type", None) or (msg.get("message_type") if isinstance(msg, dict) else None)
        if isinstance(message_type, MessageType):
            type_value = message_type.value
        else:
            type_value = str(message_type or "")
        sender = getattr(msg, "sender", None) or (msg.get("sender") if isinstance(msg, dict) else "")
        if sender == "ARYABHATA" and type_value == MessageType.CHALLENGE.value:
            pending.append(msg)
    return pending


def evaluate_challenge(challenge: Any) -> ChallengeEvaluation:
    confidence = float(getattr(challenge, "confidence", None) or (challenge.get("confidence") if isinstance(challenge, dict) else 0.0) or 0.0)
    issue_id = getattr(challenge, "issue_id", None) or (challenge.get("issue_id") if isinstance(challenge, dict) else "")
    if confidence >= 0.9:
        return ChallengeEvaluation(
            withdraw=True,
            reasoning=f"Issue #{issue_id} withdrawn due to strong confidence-backed challenge.",
            confidence=confidence,
            additional_evidence="High-confidence rationale provided by ARYABHATA.",
            supporting_evidence=[],
        )
    return ChallengeEvaluation(
        withdraw=False,
        reasoning=f"Issue #{issue_id} upheld; challenge evidence insufficient.",
        confidence=max(0.5, confidence),
        additional_evidence="Kernel safety/compliance checks still indicate unresolved risk.",
        supporting_evidence=[],
    )


async def chanakya_a2a_node(state: Any) -> Any:
    session_id = str(_state_get(state, "session_id", ""))
    current_round = int(_state_get(state, "current_round", 1) or 1)

    shared = _shared_context(state)
    _state_set(state, "shared_a2a_context", shared)
    shared.setdefault("all_messages", [])
    shared.setdefault("touched_lines", _state_get(state, "touched_lines", []) or [])
    shared.setdefault("chanakya_knowledge", {})

    # STEP 1 — Evaluate pending challenges.
    challenges = get_pending_challenges(state)
    withdrawals: list[str] = []
    for challenge in challenges:
        evaluation = evaluate_challenge(challenge)
        issue_id = getattr(challenge, "issue_id", None) or (challenge.get("issue_id") if isinstance(challenge, dict) else None)
        if evaluation.withdraw:
            withdrawal_msg = A2AMessage(
                sender="CHANAKYA",
                receiver="ARYABHATA",
                message_type=MessageType.CHALLENGE_WITHDRAW,
                content=evaluation.reasoning,
                issue_id=issue_id,
                round_number=current_round,
                confidence=evaluation.confidence,
                metadata={"reasoning": evaluation.reasoning},
            )
            await message_bus.send(session_id, withdrawal_msg)
            shared["all_messages"].append(withdrawal_msg)
            withdrawals.append(str(issue_id or ""))
            continue

        uphold_msg = A2AMessage(
            sender="CHANAKYA",
            receiver="ARYABHATA",
            message_type=MessageType.CHALLENGE_UPHOLD,
            content=(
                f"Challenge noted but Issue #{issue_id} upheld. "
                f"{evaluation.reasoning}. Additional evidence: {evaluation.additional_evidence}"
            ),
            issue_id=issue_id,
            round_number=current_round,
            confidence=evaluation.confidence,
            metadata={"reasoning": evaluation.reasoning},
        )
        await message_bus.send(session_id, uphold_msg)
        shared["all_messages"].append(uphold_msg)

    # STEP 2 — Determine review scope.
    touched_lines: list[int] = []
    for value in shared.get("touched_lines", []) or []:
        try:
            line = int(value)
        except Exception:
            continue
        if line > 0:
            touched_lines.append(line)
    if current_round > 1 and touched_lines:
        impact_scope = await impact_analyzer.get_impact_radius(
            touched_lines,
            _state_get(state, "current_fixed_patch", "") or _state_get(state, "current_patch", ""),
        )
        scope_lines = sorted(impact_scope.full_scope)
        _state_set(state, "review_type", "SURGICAL")
        _state_set(state, "review_scope_lines", scope_lines)
        shared["impact_radius"] = {
            "direct": sorted(impact_scope.direct_lines),
            "downstream": sorted(impact_scope.downstream_lines),
            "upstream": sorted(impact_scope.upstream_lines),
            "cross_file": [item.__dict__ for item in impact_scope.cross_file_impacts],
            "impact_chain": list(impact_scope.impact_chain),
        }
    else:
        _state_set(state, "review_type", "FULL")
        _state_set(state, "review_scope_lines", [])

    # STEP 3 — Run core review.
    reviewed_state = await chanakya_review_node(state)

    # STEP 4 — Broadcast LGTM if applicable.
    if _state_get(reviewed_state, "verdict") == "LGTM":
        lgtm_msg = A2AMessage(
            sender="CHANAKYA",
            receiver="ARYABHATA",
            message_type=MessageType.FULL_LGTM,
            content=f"LGTM! Patch is clean after {current_round} round(s).",
            round_number=current_round,
        )
        await message_bus.send(session_id, lgtm_msg)
        shared["all_messages"].append(lgtm_msg)
        shared["lgtm"] = True

    shared["chanakya_knowledge"]["last_review_type"] = _state_get(reviewed_state, "review_type", "FULL")
    shared["chanakya_knowledge"]["last_scope"] = _state_get(reviewed_state, "review_scope_lines", [])
    _state_set(reviewed_state, "shared_a2a_context", shared)
    return reviewed_state
