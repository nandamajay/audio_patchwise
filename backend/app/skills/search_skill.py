from __future__ import annotations

from app.skills.patchwise_skill import search_similar_patches

try:
    from app.knowledge.vector_store import PatchVectorStore
except Exception:  # pragma: no cover - fallback when vector store deps are missing
    class PatchVectorStore:  # type: ignore[override]
        def search_similar(self, query: str, n: int = 5) -> list[dict]:
            _ = (query, n)
            return []


class SearchSkill:
    """Unified search across LKML, Gerrit, and local PatchWise knowledge."""

    def __init__(self) -> None:
        self.vector_store = PatchVectorStore()

    def search(
        self,
        patch: str,
        subsystem: str,
        sources: list[str] | None = None,
    ) -> list[dict]:
        refs = search_similar_patches(patch, subsystem, sources=sources)
        local_refs = self.vector_store.search_similar(patch, n=2)
        for idx, hit in enumerate(local_refs):
            refs.append(
                {
                    "title": hit.get("title", f"Local KB Match {idx + 1}"),
                    "url": hit.get("url", "local://patchwise/kb"),
                    "author": hit.get("author", "PatchWise"),
                    "date": hit.get("date", "unknown"),
                    "relevance_score": float(hit.get("score", 0.5)),
                    "source": "local",
                }
            )
        refs.sort(key=lambda item: item.get("relevance_score", 0), reverse=True)
        return refs
