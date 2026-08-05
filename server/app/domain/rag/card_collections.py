"""ChromaDB 中的卡片 chunk 集合 —— 用于记忆卡片搜索的语义索引。

遵循与 DiaryCollectionManager 相同的模式，但使用
``card_chunks`` 集合。卡片比完整日记更简单，
因此 chunk 为单文档形式（短事件摘要 + 情绪标签无需切分）。
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import Settings
from app.domain.rag.base_collection import BaseCollectionManager, EmbeddingFunction

logger = logging.getLogger(__name__)

CARD_COLLECTION_NAME = "card_chunks"


class CardCollectionManager(BaseCollectionManager):
    """管理用于记忆卡片搜索的 ``card_chunks`` Chroma 集合。

    单用户桌面应用：一个共享集合。写入失败仅记录日志，不会抛出异常
    —— SQLite 仍是数据真源。
    """

    _collection_name = CARD_COLLECTION_NAME
    _collection_description = "Memory card text for semantic search"

    def __init__(
        self,
        settings: Settings | None = None,
        chroma_client: Any | None = None,
        embedding_function: EmbeddingFunction | None = None,
    ) -> None:
        super().__init__(
            settings=settings,
            chroma_client=chroma_client,
            embedding_function=embedding_function,
        )

    def upsert_card(
        self,
        card_id: str,
        content: str,
        *,
        emotion: str = "",
        tags: str = "",
    ) -> int:
        """索引单个卡片文档。成功返回 1，失败返回 0。"""
        if not content.strip():
            return 0

        try:
            collection = self.get_collection(create=True)
            if collection is None:
                return 0

            collection.upsert(
                ids=[f"card_{card_id}"],
                documents=[content],
                metadatas=[
                    {
                        "card_id": card_id,
                        "emotion": emotion,
                        "tags": tags,
                    }
                ],
            )
            logger.debug("Card indexed: card_id=%s", card_id)
            return 1
        except Exception as exc:
            logger.error("Chroma card upsert failed for card_id=%s: %s", card_id, exc)
            return 0

    def delete_card(self, card_id: str) -> bool:
        try:
            collection = self.get_collection(create=False)
            if collection is None:
                return False
            collection.delete(where={"card_id": card_id})
            logger.debug("Card index deleted: card_id=%s", card_id)
            return True
        except Exception as exc:
            logger.error("Chroma card delete failed for card_id=%s: %s", card_id, exc)
            return False

    def search(
        self,
        query: str,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """对卡片进行语义搜索。返回 {card_id, distance, metadata, content} 列表。"""
        try:
            collection = self.get_collection(create=False)
            if collection is None:
                return []

            results = collection.query(
                query_texts=[query],
                n_results=min(top_k, 50),
            )
            return self._format_results(results)
        except Exception as exc:
            logger.error("Card search failed: %s", exc)
            return []

    @staticmethod
    def _format_results(raw: dict[str, Any]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        if not raw or "ids" not in raw:
            return items

        ids_list = raw.get("ids") or [[]]
        distances_list = raw.get("distances") or [[]]
        metadatas_list = raw.get("metadatas") or [[]]
        documents_list = raw.get("documents") or [[]]

        flat_ids = ids_list[0] if ids_list else []
        flat_dist = distances_list[0] if distances_list else []
        flat_meta = metadatas_list[0] if metadatas_list else []
        flat_docs = documents_list[0] if documents_list else []

        for i, doc_id in enumerate(flat_ids):
            items.append(
                {
                    "card_id": (flat_meta[i].get("card_id", "") if i < len(flat_meta) else doc_id),
                    "distance": flat_dist[i] if i < len(flat_dist) else 1.0,
                    "metadata": flat_meta[i] if i < len(flat_meta) else {},
                    "content": flat_docs[i] if i < len(flat_docs) else "",
                }
            )

        return items
