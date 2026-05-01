from typing import Annotated, Literal, TypedDict

from langgraph.graph.message import add_messages


class PatchWiseState(TypedDict):
    session_id: str
    patch_input: str
    kernel_version: str
    subsystem: str
    source_path: str
    llm_provider: str
    llm_model: str
    max_rounds: int
    current_round: int
    review_findings: list[dict]
    fix_attempts: list[dict]
    similar_patches: list[dict]
    current_patch: str
    verdict: Literal["LGTM", "NEEDS_WORK", "PENDING"]
    interrupt_hint: str | None
    conversation_log: list[dict]
    quality_score: float
    latest_review: dict
    fix_history: list[dict]
    # LangGraph-native message accumulator for optional future prompt chaining.
    messages: Annotated[list[dict], add_messages]
