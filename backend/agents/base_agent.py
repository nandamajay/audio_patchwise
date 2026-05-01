from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List


class ThinkingStep(Enum):
    CHECKPATCH_ANALYSIS = "checkpatch_analysis"
    LSP_CONTEXT = "lsp_context"
    LKML_SEARCH = "lkml_search"
    COMPLIANCE_CHECK = "compliance_check"
    LOGIC_ANALYSIS = "logic_analysis"
    FIX_STRATEGY = "fix_strategy"
    CODE_GENERATION = "code_generation"
    JUSTIFICATION = "justification"
    FEEDBACK_CONTEXT = "feedback_context"


@dataclass
class ReasoningNode:
    step: ThinkingStep
    label: str
    description: str
    status: str = "pending"
    result: str = ""
    confidence: float = 0.0
    duration_ms: int = 0
    children: List["ReasoningNode"] = field(default_factory=list)
    lkml_refs: list[dict] = field(default_factory=list)


@dataclass
class AgentThoughtChain:
    agent: str
    round_num: int
    nodes: List[ReasoningNode] = field(default_factory=list)
    total_time: int = 0

    def to_dict(self) -> dict:
        def node_to_dict(node: ReasoningNode) -> dict:
            return {
                "step": node.step.value,
                "label": node.label,
                "description": node.description,
                "status": node.status,
                "result": node.result,
                "confidence": node.confidence,
                "duration_ms": node.duration_ms,
                "children": [node_to_dict(child) for child in node.children],
                "lkml_refs": node.lkml_refs,
            }

        return {
            "agent": self.agent,
            "round_num": self.round_num,
            "nodes": [node_to_dict(node) for node in self.nodes],
            "total_time": self.total_time,
        }
