"""
ChromaDB async write queue for concurrent-safe embeddings.
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

import chromadb
from chromadb.utils import embedding_functions

logger = logging.getLogger(__name__)

_chroma_path = Path(os.environ.get("CHROMADB_PATH", "data/chromadb"))
_chroma_path.mkdir(parents=True, exist_ok=True)
chroma_client = chromadb.PersistentClient(path=str(_chroma_path))
embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)

_write_queue: asyncio.Queue = asyncio.Queue()
_write_worker_task: asyncio.Task | None = None


async def kb_write_worker() -> None:
    logger.info("[ChromaDB] Write worker started")
    while True:
        task = await _write_queue.get()
        try:
            operation = task["operation"]
            collection = chroma_client.get_or_create_collection(
                task["collection"],
                embedding_function=embedding_fn,
            )

            if operation == "add":
                collection.add(
                    documents=task["documents"],
                    metadatas=task["metadatas"],
                    ids=task["ids"],
                )
            elif operation == "update":
                collection.update(
                    ids=task["ids"],
                    documents=task.get("documents"),
                    metadatas=task.get("metadatas"),
                )
            elif operation == "delete":
                collection.delete(ids=task["ids"])
        except Exception as exc:
            logger.error("[ChromaDB] Write worker error: %s", exc)
        finally:
            _write_queue.task_done()


async def start_write_worker() -> None:
    global _write_worker_task
    if _write_worker_task is None or _write_worker_task.done():
        _write_worker_task = asyncio.create_task(kb_write_worker())


async def queue_kb_write(collection: str, documents: list[str], metadatas: list[dict[str, Any]], ids: list[str]) -> None:
    await _write_queue.put(
        {
            "operation": "add",
            "collection": collection,
            "documents": documents,
            "metadatas": metadatas,
            "ids": ids,
        }
    )


async def search_kb(collection: str, query: str, n_results: int = 5, where: dict[str, Any] | None = None) -> dict[str, Any] | list:
    try:
        col = chroma_client.get_or_create_collection(
            collection,
            embedding_function=embedding_fn,
        )
        return col.query(
            query_texts=[query],
            n_results=n_results,
            where=where,
        )
    except Exception as exc:
        logger.error("[ChromaDB] Search failed: %s", exc)
        return []


async def get_kb_stats() -> dict[str, Any]:
    try:
        audio_col = chroma_client.get_or_create_collection(
            "audio_patches",
            embedding_function=embedding_fn,
        )
        patterns_col = chroma_client.get_or_create_collection(
            "fix_patterns",
            embedding_function=embedding_fn,
        )
        return {
            "audio_patches_count": audio_col.count(),
            "fix_patterns_count": patterns_col.count(),
            "storage_path": str(_chroma_path),
            "write_queue_size": _write_queue.qsize(),
            "status": "healthy",
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
