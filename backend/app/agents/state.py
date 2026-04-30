from typing import Annotated, TypedDict, Literal
from langgraph.graph.message import add_messages

class PatchWiseState(TypedDict):
    session_id: str
    patch_input: str                     # raw patch text
    kernel_version: str
    subsystem: str                       # e.g., "alsa-asoc"
    source_path: str
    llm_model: str
    max_rounds: int
    current_round: int
    review_findings: list[dict]          # CHANAKYA findings per round
    fix_attempts: list[dict]             # ARYABHATA fixes per round
    similar_patches: list[dict]          # found LKML/Gerrit references
    current_patch: str                   # latest patch version
    verdict: Literal["LGTM", "NEEDS_WORK", "PENDING"]
    interrupt_hint: str | None           # soft interrupt message
    conversation_log: list[dict]         # full chat log for export
    quality_score: float                 # patch quality 0-100
