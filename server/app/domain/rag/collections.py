"""ChromaDB 中的日记 chunk 集合生命周期管理。"""

from __future__ import annotations

import logging
from typing import Any

from app.config import Settings
from app.domain.rag.base_collection import BaseCollectionManager, EmbeddingFunction
from app.domain.rag.chunker import ChunkSplitter
from app.domain.rag.types import Chunk

logger = logging.getLogger(__name__)

COLLECTION_NAME = "diary_chunks"


class DiaryCollectionManager(BaseCollectionManager):
    """管理用于日记 CRUD 同步的 ``diary_chunks`` Chroma 集合。

    单用户桌面应用：一个共享集合，无按用户前缀。
    写入失败仅记录日志，不会抛出异常（SQLite 仍是数据真源）。
    """

    _collection_name = COLLECTION_NAME
    _collection_description = "Diary text chunks for hybrid RAG"

    def __init__(
        self,
        settings: Settings | None = None,
        chroma_client: Any | None = None,
        embedding_function: EmbeddingFunction | None = None,
        chunk_splitter: ChunkSplitter | None = None,
        *,
        parent_child: bool = False,
    ) -> None:
        super().__init__(
            settings=settings,
            chroma_client=chroma_client,
            embedding_function=embedding_function,
        )
        self._splitter = chunk_splitter or ChunkSplitter(parent_child=parent_child)

    def upsert_diary(
        self,
        diary_id: str,
        content: str,
        *,
        date: str = "",
        tags: str = "",
    ) -> int:
        """对日记条目进行分块并 upsert。返回写入的 chunk 数量。"""
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
        """替换一条日记的全部 chunk（先删除再 upsert）。"""
        self.delete_diary(diary_id)
        return self.upsert_diary(diary_id, content, date=date, tags=tags)

    def delete_diary(self, diary_id: str) -> bool:
        """移除属于 ``diary_id`` 的全部 chunk。"""
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
