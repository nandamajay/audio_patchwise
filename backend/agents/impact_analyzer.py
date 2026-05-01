"""
ImpactAnalyzer — Smart surgical scope builder.
Detects cross-line impact from touched lines.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


def classify_lsp_impact(ref) -> str:
    kind = str(getattr(ref, "kind", "") or "").lower()
    if "call" in kind:
        return "DATA_FLOW"
    if "return" in kind:
        return "RETURN_VALUE"
    return "DATA_FLOW"


@dataclass
class CrossLineImpact:
    affected_line: int
    affecting_line: int
    impact_type: str
    symbol: str
    description: str
    severity: str
    chain_depth: int = 0


@dataclass
class ImpactRadius:
    direct_lines: Set[int] = field(default_factory=set)
    downstream_lines: Set[int] = field(default_factory=set)
    upstream_lines: Set[int] = field(default_factory=set)
    cross_file_impacts: List[CrossLineImpact] = field(default_factory=list)
    impact_chain: List[Tuple[int, int, str]] = field(default_factory=list)

    @property
    def full_scope(self) -> Set[int]:
        return self.direct_lines | self.downstream_lines | self.upstream_lines


class ImpactAnalyzer:
    NEIGHBOR_RADIUS = 10

    def __init__(self, lsp_client=None):
        self.lsp_client = lsp_client

    async def get_impact_radius(
        self,
        changed_lines: List[int],
        patch_content: str,
        max_depth: int = 10,
    ) -> ImpactRadius:
        direct = self._get_neighbors(changed_lines, patch_content)
        modified_symbols = self._extract_modified_symbols(changed_lines, patch_content)

        downstream: Set[int] = set()
        frontier = set(changed_lines)
        visited = set(changed_lines)
        depth = 0
        while frontier and depth < max_depth:
            new_frontier: Set[int] = set()
            for line in frontier:
                next_lines = self._trace_forward(line, patch_content, modified_symbols)
                fresh = next_lines - visited
                downstream.update(fresh)
                new_frontier.update(fresh)
                visited.update(fresh)
            frontier = new_frontier
            depth += 1

        upstream = self._trace_backward(changed_lines, patch_content, modified_symbols)
        impact_chain = self._build_impact_chain(
            changed_lines, downstream, patch_content, modified_symbols
        )

        cross_file: List[CrossLineImpact] = []
        if self.lsp_client:
            cross_file = await self._get_cross_file_impacts(modified_symbols, patch_content)

        return ImpactRadius(
            direct_lines=direct,
            downstream_lines=downstream,
            upstream_lines=upstream,
            cross_file_impacts=cross_file,
            impact_chain=impact_chain,
        )

    def _get_neighbors(self, changed_lines: List[int], patch_content: str) -> Set[int]:
        neighbors: Set[int] = set()
        total_lines = len(patch_content.split("\n"))
        for line in changed_lines:
            start = max(1, line - self.NEIGHBOR_RADIUS)
            end = min(total_lines, line + self.NEIGHBOR_RADIUS)
            neighbors.update(range(start, end + 1))
        return neighbors

    def _extract_modified_symbols(
        self,
        changed_lines: List[int],
        patch_content: str,
    ) -> Dict[str, dict]:
        symbols: Dict[str, dict] = {}
        patch_lines = patch_content.split("\n")

        for line_no in changed_lines:
            if line_no <= 0 or line_no > len(patch_lines):
                continue

            old_line = None
            new_line = None
            idx = line_no - 1
            window_start = max(0, idx - 3)
            window_end = min(len(patch_lines), idx + 4)
            for line in patch_lines[window_start:window_end]:
                if line.startswith("-") and not line.startswith("---"):
                    old_line = line[1:].strip()
                elif line.startswith("+") and not line.startswith("+++"):
                    new_line = line[1:].strip()

            if not (old_line and new_line):
                continue

            old_ret = re.match(r"return\s+(-?\w+)\s*;", old_line)
            new_ret = re.match(r"return\s+(-?\w+)\s*;", new_line)
            if old_ret and new_ret and old_ret.group(1) != new_ret.group(1):
                symbols[f"return_value_line_{line_no}"] = {
                    "type": "return_value",
                    "old_value": old_ret.group(1),
                    "new_value": new_ret.group(1),
                    "line": line_no,
                }

            var_match = re.match(r"(\w+)\s*=\s*(.*);", old_line)
            if var_match:
                symbols[var_match.group(1)] = {
                    "type": "variable",
                    "old_value": var_match.group(2),
                    "line": line_no,
                }

        return symbols

    def _trace_forward(
        self,
        line_no: int,
        patch_content: str,
        modified_symbols: Dict[str, dict],
    ) -> Set[int]:
        affected: Set[int] = set()
        patch_lines = patch_content.split("\n")
        for symbol_name, symbol_info in modified_symbols.items():
            if symbol_info.get("type") == "return_value":
                old_val = str(symbol_info.get("old_value", ""))
                for idx, line in enumerate(patch_lines, start=1):
                    if idx <= line_no:
                        continue
                    if old_val and old_val in line and (
                        "if" in line
                        or "switch" in line
                        or "case" in line
                        or "==" in line
                        or "!=" in line
                    ):
                        affected.add(idx)
            elif symbol_info.get("type") == "variable":
                for idx, line in enumerate(patch_lines, start=1):
                    if idx > line_no and symbol_name in line:
                        affected.add(idx)
        return affected

    def _trace_backward(
        self,
        changed_lines: List[int],
        patch_content: str,
        modified_symbols: Dict[str, dict],
    ) -> Set[int]:
        del modified_symbols
        dependencies: Set[int] = set()
        patch_lines = patch_content.split("\n")
        for line_no in changed_lines:
            if line_no <= 0 or line_no > len(patch_lines):
                continue
            line = patch_lines[line_no - 1]
            identifiers = re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", line)
            for identifier in identifiers:
                for idx, prev in enumerate(patch_lines[: line_no - 1], start=1):
                    if f"{identifier} =" in prev or f"{identifier}=" in prev:
                        dependencies.add(idx)
        return dependencies

    def _build_impact_chain(
        self,
        changed_lines: List[int],
        downstream: Set[int],
        patch_content: str,
        modified_symbols: Dict[str, dict],
    ) -> List[Tuple[int, int, str]]:
        del patch_content
        chain: list[Tuple[int, int, str]] = []
        for line_no in changed_lines:
            for downstream_line in sorted(downstream):
                for symbol_info in modified_symbols.values():
                    if symbol_info.get("type") == "return_value":
                        chain.append(
                            (
                                line_no,
                                downstream_line,
                                (
                                    f"return value {symbol_info.get('old_value')} -> "
                                    f"{symbol_info.get('new_value')} affects check at line {downstream_line}"
                                ),
                            )
                        )
        return chain

    async def _get_cross_file_impacts(
        self,
        modified_symbols: Dict[str, dict],
        patch_content: str,
    ) -> List[CrossLineImpact]:
        del patch_content
        impacts: list[CrossLineImpact] = []
        if not self.lsp_client:
            return impacts

        for symbol_name, symbol_info in modified_symbols.items():
            try:
                refs = await self.lsp_client.find_references(symbol_name)
            except Exception:
                continue
            for ref in refs:
                impacts.append(
                    CrossLineImpact(
                        affected_line=int(getattr(ref, "line", 0) or 0),
                        affecting_line=int(symbol_info.get("line", 0) or 0),
                        impact_type=classify_lsp_impact(ref),
                        symbol=symbol_name,
                        description=f"{symbol_name} used at {getattr(ref, 'file', '?')}:{getattr(ref, 'line', '?')}",
                        severity="WARNING",
                    )
                )
        return impacts


impact_analyzer = ImpactAnalyzer()
