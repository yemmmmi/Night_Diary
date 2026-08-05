"""Card chunk collection in ChromaDB — semantic index for memory card search.

Follows the same pattern as DiaryCollectionManager but uses
``card_chunks`` collection.  Cards are simpler than full diaries
so chunks are single-document (no splitting needed for short
event summaries + emotion labels).
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import Settings
from app.domain.rag.base_collection import BaseCollectionManager, EmbeddingFunction

logger = logging.getLogger(__name__)

CARD_COLLECTION_NAME = "card_chunks"


class CardCollectionManager(BaseCollectionManager):
    """Manage the ``card_chunks`` Chroma collection for memory card search.

    Single-user desktop app: one shared collection.  Write failures are
    logged and do not raise — SQLite remains the source of truth.
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
        """Index a single card document.  Returns 1 on success, 0 on failure."""
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
        """Semantic search cards.  Returns list of {card_id, distance, metadata, content}."""
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
