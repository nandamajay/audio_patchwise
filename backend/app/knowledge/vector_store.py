from __future__ import annotations

from typing import Any


class PatchVectorStore:
    """Lightweight ChromaDB wrapper with in-memory fallback."""

    def __init__(
        self,
        collection_name: str = "patchwise_alsa_asoc",
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
    ) -> None:
        self.collection_name = collection_name
        self.embedding_model = embedding_model
        self._fallback_docs: list[dict[str, Any]] = []
        self._collection = None

        try:
            import chromadb

            client = chromadb.Client()
            self._collection = client.get_or_create_collection(name=collection_name)
        except Exception:
            self._collection = None

    def add_patch(self, document: dict[str, Any]) -> None:
        payload = {
            "patch_id": document.get("patch_id", "unknown"),
            "title": document.get("title", "Untitled patch"),
            "author": document.get("author", "unknown"),
            "date": document.get("date", "unknown"),
            "subsystem": document.get("subsystem", "alsa-asoc"),
            "verdict": document.get("verdict", "PENDING"),
            "url": document.get("url", "local://patchwise/unknown"),
            "content": document.get("content", ""),
        }

        if self._collection is None:
            self._fallback_docs.append(payload)
            return

        self._collection.add(
            ids=[payload["patch_id"]],
            documents=[payload["content"]],
            metadatas=[
                {
                    "title": payload["title"],
                    "author": payload["author"],
                    "date": payload["date"],
                    "subsystem": payload["subsystem"],
                    "verdict": payload["verdict"],
                    "url": payload["url"],
                    "embedding_model": self.embedding_model,
                }
            ],
        )

    def search_similar(self, query: str, n: int = 5) -> list[dict[str, Any]]:
        if self._collection is None:
            results: list[dict[str, Any]] = []
            for doc in self._fallback_docs[:n]:
                score = 0.5
                if query and doc["content"]:
                    overlap = len(set(query.split()) & set(doc["content"].split()))
                    score = min(0.99, 0.5 + overlap / 100.0)
                results.append(
                    {
                        "patch_id": doc["patch_id"],
                        "title": doc["title"],
                        "author": doc["author"],
                        "date": doc["date"],
                        "subsystem": doc["subsystem"],
                        "url": doc["url"],
                        "score": round(score, 3),
                    }
                )
            return results

        raw = self._collection.query(query_texts=[query], n_results=n)
        ids = raw.get("ids", [[]])[0]
        metadatas = raw.get("metadatas", [[]])[0]
        distances = raw.get("distances", [[]])[0]

        output: list[dict[str, Any]] = []
        for idx, patch_id in enumerate(ids):
            metadata = metadatas[idx] if idx < len(metadatas) else {}
            distance = distances[idx] if idx < len(distances) else 1.0
            output.append(
                {
                    "patch_id": patch_id,
                    "title": metadata.get("title", "Untitled patch"),
                    "author": metadata.get("author", "unknown"),
                    "date": metadata.get("date", "unknown"),
                    "subsystem": metadata.get("subsystem", "alsa-asoc"),
                    "url": metadata.get("url", "local://patchwise/unknown"),
                    "score": round(max(0.0, 1.0 - float(distance)), 3),
                }
            )
        return output

    def update_from_session(self, session_state: dict[str, Any]) -> None:
        session_id = session_state.get("session_id", "unknown")
        current_patch = session_state.get("current_patch", "")
        verdict = session_state.get("verdict", "PENDING")
        subsystem = session_state.get("subsystem", "alsa-asoc")

        self.add_patch(
            {
                "patch_id": f"session-{session_id}",
                "title": f"Session {session_id} final patch",
                "author": "PatchWise Session",
                "date": "current",
                "subsystem": subsystem,
                "verdict": verdict,
                "url": f"local://patchwise/session/{session_id}",
                "content": current_patch,
            }
        )

        # Store CHANAKYA findings as searchable known issues.
        for round_item in session_state.get("review_findings", []):
            round_id = round_item.get("round", 0)
            for idx, finding in enumerate(round_item.get("findings", [])):
                self.add_patch(
                    {
                        "patch_id": f"finding-{session_id}-{round_id}-{idx}",
                        "title": f"Known issue: {finding.get('issue_type', 'UNKNOWN')}",
                        "author": "CHANAKYA",
                        "date": "current",
                        "subsystem": subsystem,
                        "verdict": "KNOWN_ISSUE",
                        "url": f"local://patchwise/session/{session_id}/round/{round_id}/finding/{idx}",
                        "content": finding.get("description", ""),
                    }
                )
