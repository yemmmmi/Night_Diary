"""Diary chunk collection lifecycle in ChromaDB."""

from __future__ import annotations

import logging
from typing import Any, Protocol

from app.config import Settings, get_settings
from app.domain.knowledge.store import get_chroma_client
from app.domain.rag.chunker import ChunkSplitter
from app.domain.rag.types import Chunk

logger = logging.getLogger(__name__)

COLLECTION_NAME = "diary_chunks"


class EmbeddingFunction(Protocol):
    def __call__(self, input: list[str]) -> list[list[float]]: ...


class DiaryCollectionManager:
    """Manage the ``diary_chunks`` Chroma collection for diary CRUD sync.

    Single-user desktop app: one shared collection, no per-user prefix.
    Write failures are logged and do not raise (SQLite remains source of truth).
    """

    def __init__(
        self,
        settings: Settings | None = None,
        chroma_client: Any | None = None,
        embedding_function: EmbeddingFunction | None = None,
        chunk_splitter: ChunkSplitter | None = None,
        *,
        parent_child: bool = False,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = chroma_client
        self._embedding_function = embedding_function
        self._splitter = chunk_splitter or ChunkSplitter(parent_child=parent_child)
        self._collection: Any | None = None

    def _resolve_client(self) -> Any:
        if self._client is not None:
            return self._client
        return get_chroma_client(self._settings.chroma_persist_dir)

    def _collection_kwargs(self) -> dict[str, Any]:
        if self._embedding_function is not None:
            return {"embedding_function": self._embedding_function}
        return {}

    def get_collection(self, *, create: bool = False) -> Any | None:
        """Return the diary chunks collection, optionally creating it."""
        if self._collection is not None:
            return self._collection

        client = self._resolve_client()
        kwargs = self._collection_kwargs()

        try:
            if create:
                self._collection = client.get_or_create_collection(
                    name=COLLECTION_NAME,
                    metadata={"description": "Diary text chunks for hybrid RAG"},
                    **kwargs,
                )
            else:
                self._collection = client.get_collection(name=COLLECTION_NAME, **kwargs)
        except Exception as exc:
            logger.warning("Diary collection '%s' unavailable: %s", COLLECTION_NAME, exc)
            return None

        return self._collection

    def upsert_diary(
        self,
        diary_id: str,
        content: str,
        *,
        date: str = "",
        tags: str = "",
    ) -> int:
        """Chunk and upsert a diary entry. Returns the number of chunks written."""
        if not content.strip():
            return 0

        try:
            collection = self.get_collection(create=True)
            if collection is None:
                return 0

            chunks = self._splitter.split_chunks(
                content,
                diary_id=diary_id,
                date=date,
                tags=tags,
            )
            if not chunks:
                return 0

            collection.upsert(
                ids=[chunk.doc_id for chunk in chunks],
                documents=[chunk.content for chunk in chunks],
                metadatas=[self._chunk_metadata(chunk) for chunk in chunks],
            )
            logger.debug(
                "Diary chunks upserted: diary_id=%s count=%d",
                diary_id,
                len(chunks),
            )
            return len(chunks)
        except Exception as exc:
            logger.error("Chroma upsert failed for diary_id=%s: %s", diary_id, exc)
            return 0

    def update_diary(
        self,
        diary_id: str,
        content: str,
        *,
        date: str = "",
        tags: str = "",
    ) -> int:
        """Replace all chunks for a diary (delete then upsert)."""
        self.delete_diary(diary_id)
        return self.upsert_diary(diary_id, content, date=date, tags=tags)

    def delete_diary(self, diary_id: str) -> bool:
        """Remove all chunks belonging to ``diary_id``."""
        try:
            collection = self.get_collection(create=False)
            if collection is None:
                return False

            collection.delete(where={"diary_id": diary_id})
            logger.debug("Diary chunks deleted: diary_id=%s", diary_id)
            return True
        except Exception as exc:
            logger.error("Chroma delete failed for diary_id=%s: %s", diary_id, exc)
            return False

    def count(self) -> int:
        """Return total chunk count in the collection."""
        collection = self.get_collection(create=False)
        if collection is None:
            return 0
        try:
            return int(collection.count())
        except Exception:
            return 0

    @staticmethod
    def _chunk_metadata(chunk: Chunk) -> dict[str, str | int]:
        metadata: dict[str, str | int] = {
            "diary_id": chunk.diary_id,
            "date": chunk.date,
            "tags": chunk.tags,
            "chunk_index": chunk.chunk_index,
            "chunk_total": chunk.chunk_total,
            "doc_type": chunk.doc_type,
        }
        if chunk.parent_id:
            metadata["parent_id"] = chunk.parent_id
        return metadata
