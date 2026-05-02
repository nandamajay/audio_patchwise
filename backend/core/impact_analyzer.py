from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ImpactResult:
    touched_lines: list[int]
    direct_neighbors: list[int] = field(default_factory=list)
    symbol_hits: dict[str, list[int]] = field(default_factory=dict)
    forward_flow: list[int] = field(default_factory=list)
    backward_deps: list[int] = field(default_factory=list)
    transitive_chain: list[int] = field(default_factory=list)
    cross_file_impact: list[dict[str, Any]] = field(default_factory=list)

    @property
    def impact_radius(self) -> dict[str, Any]:
        return {
            "direct": self.direct_neighbors,
            "downstream": self.forward_flow,
            "upstream": self.backward_deps,
            "cross_file": self.cross_file_impact,
            "impact_chain": self.transitive_chain,
        }


class ImpactAnalyzer:
    def __init__(self, lsp_client: Any | None = None):
        self.lsp_client = lsp_client

    def get_line_neighbors(self, changed_lines: list[int], radius: int = 10) -> list[int]:
        neighbors: set[int] = set()
        for line in changed_lines:
            start = max(1, int(line) - radius)
            end = max(start, int(line) + radius)
            neighbors.update(range(start, end + 1))
        return sorted(neighbors)

    def extract_modified_symbols(self, patch_content: str) -> dict[str, list[int]]:
        symbols: dict[str, list[int]] = {}
        for idx, line in enumerate((patch_content or "").splitlines(), start=1):
            if not line.startswith("+") or line.startswith("+++"):
                continue
            for name in re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", line):
                symbols.setdefault(name, []).append(idx)
        return symbols

    def trace_symbol_usage(self, patch_content: str, symbols: dict[str, list[int]]) -> tuple[list[int], list[int]]:
        lines = (patch_content or "").splitlines()
        forward_flow: set[int] = set()
        backward_dep: set[int] = set()
        for name, origin_lines in symbols.items():
            first_line = min(origin_lines) if origin_lines else 1
            for idx, line in enumerate(lines, start=1):
                if name not in line:
                    continue
                if idx > first_line:
                    forward_flow.add(idx)
                elif idx < first_line:
                    backward_dep.add(idx)
        return sorted(forward_flow), sorted(backward_dep)

    def transitive_closure(self, seed_lines: list[int], full_chain: list[int]) -> list[int]:
        closure = set(seed_lines)
        frontier = set(seed_lines)
        chain = set(full_chain)
        while frontier:
            current = frontier.pop()
            for candidate in chain:
                if abs(candidate - current) <= 10 and candidate not in closure:
                    closure.add(candidate)
                    frontier.add(candidate)
        return sorted(closure)

    async def lsp_cross_file_impact(self, symbols: dict[str, list[int]]) -> list[dict[str, Any]]:
        impacts: list[dict[str, Any]] = []
        if not self.lsp_client:
            return impacts
        for symbol in symbols:
            try:
                refs = await self.lsp_client.find_references(symbol)
            except Exception:
                refs = []
            for ref in refs:
                impacts.append(
                    {
                        "symbol": symbol,
                        "file": getattr(ref, "file", ""),
                        "line": getattr(ref, "line", 0),
                        "description": f"find_references lsp hit for {symbol}",
                    }
                )
        return impacts

    async def analyze(self, changed_lines: list[int], patch_content: str) -> ImpactResult:
        neighbors = self.get_line_neighbors(changed_lines, radius=10)
        symbols = self.extract_modified_symbols(patch_content)
        forward_flow, backward_dep = self.trace_symbol_usage(patch_content, symbols)
        full_chain = sorted(set(neighbors) | set(forward_flow) | set(backward_dep))
        transitive = self.transitive_closure(changed_lines, full_chain)
        cross_file = await self.lsp_cross_file_impact(symbols)
        return ImpactResult(
            touched_lines=changed_lines,
            direct_neighbors=neighbors,
            symbol_hits=symbols,
            forward_flow=forward_flow,
            backward_deps=backward_dep,
            transitive_chain=transitive,
            cross_file_impact=cross_file,
        )


impact_analyzer = ImpactAnalyzer()
