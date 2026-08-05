"""基于 ChromaDB 的心理学领域知识存储。"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Protocol

from app.config import Settings, get_settings
from app.domain.knowledge.types import KnowledgeHit

logger = logging.getLogger(__name__)

COLLECTION_NAME = "domain_knowledge_psychology"
DEFAULT_MAX_RESULTS = 2
REFERENCE_NOTE = "【通用知识参考】"

_chroma_client: Any | None = None


def get_chroma_client(persist_dir: str) -> Any:
    """返回进程级别的 Chroma ``PersistentClient`` 单例。

    ``anonymized_telemetry=False`` 禁用 chromadb 的匿名使用情况上报
    （posthog）。这是一个个人日记应用 — 无需遥测，同时也可避免
    chromadb 0.5.x × posthog 7.x 的 API 不兼容问题。
    """
    global _chroma_client
    if _chroma_client is None:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        settings = ChromaSettings(anonymized_telemetry=False)
        _chroma_client = chromadb.PersistentClient(
            path=persist_dir, settings=settings
        )
    return _chroma_client


def reset_chroma_client() -> None:
    """清除缓存的客户端 — 仅用于测试。"""
    global _chroma_client
    _chroma_client = None


class EmbeddingFunction(Protocol):
    def __call__(self, input: list[str]) -> list[list[float]]: ...


class DomainKnowledgeStore:
    """共享心理学领域知识集合的读/写接口。

    所有智能体必须通过此类查询领域知识（单一入口点）。
    查询失败会降级为返回空结果列表，不会抛出异常。
    """

    def __init__(
        self,
        settings: Settings | None = None,
        chroma_client: Any | None = None,
        embedding_function: EmbeddingFunction | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = chroma_client
        self._embedding_function = embedding_function
        self._collection: Any | None = None

    def _resolve_client(self) -> Any:
        if self._client is not None:
            return self._client
        return get_chroma_client(self._settings.chroma_persist_dir)

    def _collection_kwargs(self) -> dict[str, Any]:
        if self._embedding_function is not None:
            return {"embedding_function": self._embedding_function}
        return {}

    def _get_collection(self, *, create: bool = False) -> Any | None:
        if self._collection is not None:
            return self._collection

        client = self._resolve_client()
        kwargs = self._collection_kwargs()

        try:
            if create:
                self._collection = client.get_or_create_collection(
                    name=COLLECTION_NAME,
                    **kwargs,
                )
            else:
                self._collection = client.get_collection(name=COLLECTION_NAME, **kwargs)
        except Exception as exc:
            logger.warning(
                "Domain knowledge collection '%s' unavailable: %s",
                COLLECTION_NAME,
                exc,
            )
            return None

        return self._collection

    def query(
        self,
        query_text: str,
        max_results: int = DEFAULT_MAX_RESULTS,
        category_filter: str | None = None,
    ) -> list[KnowledgeHit]:
        """检索与 ``query_text`` 相关的领域知识条目。"""
        if not query_text.strip():
            return []

        started = time.perf_counter()
        hits: list[KnowledgeHit] = []

        try:
            collection = self._get_collection(create=False)
            if collection is None:
                return []

            query_params: dict[str, Any] = {
                "query_texts": [query_text],
                "n_results": max_results,
                "include": ["documents", "metadatas", "distances"],
            }
            if category_filter:
                query_params["where"] = {"category": category_filter}

            results = collection.query(**query_params)
            hits = self._format_hits(results)
            return hits

        except Exception as exc:
            logger.error("Domain knowledge query failed: %s", exc)
            return []

        finally:
            self._log_query_trace(query_text, hits, started)

    def add(
        self,
        content: str,
        *,
        category: str,
        topic: str,
        source: str,
        doc_id: str | None = None,
    ) -> str | None:
        """插入一条领域知识文档。返回文档 id。"""
        if not content.strip():
            return None

        collection = self._get_collection(create=True)
        if collection is None:
            return None

        resolved_id = doc_id or str(uuid.uuid4())
        collection.add(
            ids=[resolved_id],
            documents=[content],
            metadatas=[{"category": category, "topic": topic, "source": source}],
        )
        return resolved_id

    def delete(self, doc_id: str) -> bool:
        """按 id 删除领域知识文档。"""
        if not doc_id.strip():
            return False

        collection = self._get_collection(create=False)
        if collection is None:
            return False

        try:
            collection.delete(ids=[doc_id])
            return True
        except Exception as exc:
            logger.error("Domain knowledge delete failed for id=%s: %s", doc_id, exc)
            return False

    def is_initialized(self) -> bool:
        """当集合存在且包含文档时返回 True。"""
        try:
            collection = self._get_collection(create=False)
            if collection is None:
                return False
            count = int(collection.count())
            return count > 0
        except Exception:
            return False

    def get_stats(self) -> dict[str, Any]:
        """返回基本的集合统计信息。"""
        try:
            collection = self._get_collection(create=False)
            if collection is None:
                return {"initialized": False, "count": 0}
            count = collection.count()
            return {"initialized": count > 0, "count": count}
        except Exception as exc:
            return {"initialized": False, "count": 0, "error": str(exc)}

    @staticmethod
    def _format_hits(results: dict[str, Any]) -> list[KnowledgeHit]:
        ids = results.get("ids") or [[]]
        documents = results.get("documents") or [[]]
        metadatas = results.get("metadatas") or [[]]
        distances = results.get("distances") or [[]]

        if not ids or not ids[0]:
            return []

        hits: list[KnowledgeHit] = []
        for index, doc_id in enumerate(ids[0]):
            metadata = metadatas[0][index] if metadatas and metadatas[0] else {}
            distance = distances[0][index] if distances and distances[0] else None
            document = documents[0][index] if documents and documents[0] else ""

            hits.append(
                KnowledgeHit(
                    content=document,
                    category=str(metadata.get("category", "")),
                    topic=str(metadata.get("topic", "")),
                    source=str(metadata.get("source", "")),
                    distance=float(distance) if distance is not None else None,
                    doc_id=str(doc_id),
                    reference_note=REFERENCE_NOTE,
                )
            )
        return hits

    @staticmethod
    def _log_query_trace(
        query_text: str,
        hits: list[KnowledgeHit],
        started: float,
    ) -> None:
        latency_ms = (time.perf_counter() - started) * 1000
        top_score: float | None = None
        if hits:
            distances = [hit.distance for hit in hits if hit.distance is not None]
            if distances:
                top_score = max(0.0, 1.0 - min(distances))

        logger.info(
            "domain_knowledge.query query_text=%r hit_count=%d top_score=%s latency_ms=%.2f",
            query_text[:100],
            len(hits),
            f"{top_score:.4f}" if top_score is not None else "none",
            latency_ms,
        )


_store: DomainKnowledgeStore | None = None


def get_domain_store(settings: Settings | None = None) -> DomainKnowledgeStore:
    """返回进程级别的 ``DomainKnowledgeStore`` 单例。"""
    global _store
    if _store is None:
        _store = DomainKnowledgeStore(settings=settings)
    return _store


def reset_domain_store() -> None:
    """清除缓存的存储 — 仅用于测试。"""
    global _store
    _store = None
