"""Hybrid retrieval: dense vector + BM25 keyword fusion with optional rerank."""

from __future__ import annotations

import dataclasses
import logging
import time
from typing import Any

from app.domain.rag.bm25 import BM25Index
from app.domain.rag.collections import DiaryCollectionManager
from app.domain.rag.reranker import Reranker
from app.domain.rag.types import RetrievalResult

logger = logging.getLogger(__name__)

DEFAULT_SEMANTIC_TOP_K = 20
DEFAULT_BM25_TOP_K = 20
DEFAULT_FINAL_TOP_K = 5
DEFAULT_RRF_K = 60


def reciprocal_rank_fusion(
    ranked_lists: list[list[RetrievalResult]],
    *,
    k: int = DEFAULT_RRF_K,
) -> list[RetrievalResult]:
    """Fuse multiple ranked lists via Reciprocal Rank Fusion.

    ``score(d) = Σ 1 / (k + rank_i(d))``, deduplicated by ``doc_id``.
    """
    rrf_scores: dict[str, float] = {}
    doc_map: dict[str, RetrievalResult] = {}

    for ranked_list in ranked_lists:
        for rank, doc in enumerate(ranked_list):
            if not doc.doc_id:
                continue
            rrf_scores[doc.doc_id] = rrf_scores.get(doc.doc_id, 0.0) + 1.0 / (k + rank + 1)
            if doc.doc_id not in doc_map:
                doc_map[doc.doc_id] = doc

    fused = [
        dataclasses.replace(doc_map[doc_id], rrf_score=score, score=score)
        for doc_id, score in rrf_scores.items()
    ]
    fused.sort(key=lambda result: result.score, reverse=True)
    return fused


class HybridRetriever:
    """Orchestrate dense + sparse retrieval over the diary chunk collection.

    Dependencies are injected (B-2 :class:`DiaryCollectionManager` +
    :class:`BM25Index`, optional B-3 :class:`Reranker`). Each ``retrieve`` call
    emits a trace log with per-stage result counts and latency.
    """

    def __init__(
        self,
        collection_manager: DiaryCollectionManager,
        bm25_index: BM25Index,
        reranker: Reranker | None = None,
        *,
        semantic_top_k: int = DEFAULT_SEMANTIC_TOP_K,
        bm25_top_k: int = DEFAULT_BM25_TOP_K,
        final_top_k: int = DEFAULT_FINAL_TOP_K,
        rrf_k: int = DEFAULT_RRF_K,
    ) -> None:
        self._collections = collection_manager
        self._bm25 = bm25_index
        self._reranker = reranker
        self.semantic_top_k = semantic_top_k
        self.bm25_top_k = bm25_top_k
        self.final_top_k = final_top_k
        self.rrf_k = rrf_k

    def retrieve(self, query: str, *, top_k: int | None = None) -> list[RetrievalResult]:
        """Return the most relevant diaries for ``query`` (deduped by ``diary_id``)."""
        if not query.strip():
            return []

        limit = top_k if top_k is not None else self.final_top_k
        started = time.perf_counter()

        vector_results = self._filter_orphan_vectors(self._vector_search(query))
        bm25_results = self._bm25_search(query)

        ranked_lists = [results for results in (vector_results, bm25_results) if results]
        if not ranked_lists:
            self._log_trace(query, 0, 0, 0, started)
            return []

        fused = reciprocal_rank_fusion(ranked_lists, k=self.rrf_k)

        ranked = self._reranker.rerank(query, fused) if self._reranker is not None else fused
        deduped = self._dedupe_by_diary(ranked)[:limit]

        self._log_trace(
            query,
            len(vector_results),
            len(bm25_results),
            len(fused),
            started,
        )
        return deduped

    def _vector_search(self, query: str) -> list[RetrievalResult]:
        collection = self._collections.get_collection(create=False)
        if collection is None:
            return []

        try:
            count = int(collection.count())
            if count == 0:
                return []
            results = collection.query(
                query_texts=[query],
                n_results=min(self.semantic_top_k, count),
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            logger.warning("Vector search failed; degrading to BM25 only: %s", exc)
            return []

        return self._format_vector_hits(results)

    def _filter_orphan_vectors(self, hits: list[RetrievalResult]) -> list[RetrievalResult]:
        """Remove vector hits whose doc_id no longer exists in the BM25 index.

        ChromaDB deletion can fail silently, leaving orphan vectors that
        reference deleted diaries. The BM25 index is built from SQLite and
        is always consistent, so we use it as the source of truth.
        """
        if not hits:
            return hits
        known_ids = self._bm25.known_doc_ids()
        if not known_ids:
            # BM25 index is empty — can't validate, return as-is
            return hits
        filtered = [h for h in hits if h.doc_id in known_ids]
        if len(filtered) < len(hits):
            dropped = len(hits) - len(filtered)
            logger.info("Filtered %d orphan vector(s) not in BM25 index", dropped)
        return filtered

    @staticmethod
    def _format_vector_hits(results: dict[str, Any]) -> list[RetrievalResult]:
        ids = results.get("ids") or [[]]
        if not ids or not ids[0]:
            return []

        documents = results.get("documents") or [[]]
        metadatas = results.get("metadatas") or [[]]
        distances = results.get("distances") or [[]]

        hits: list[RetrievalResult] = []
        for index, doc_id in enumerate(ids[0]):
            metadata = metadatas[0][index] if metadatas and metadatas[0] else {}
            distance = distances[0][index] if distances and distances[0] else None
            document = documents[0][index] if documents and documents[0] else ""
            score = 1.0 - float(distance) if distance is not None else 0.0
            hits.append(
                RetrievalResult(
                    doc_id=str(doc_id),
                    content=document,
                    diary_id=str(metadata.get("diary_id", "")),
                    score=score,
                    chunk_index=int(metadata.get("chunk_index", 0)),
                    chunk_total=int(metadata.get("chunk_total", 1)),
                    date=str(metadata.get("date", "")),
                    tags=str(metadata.get("tags", "")),
                )
            )
        return hits

    def _bm25_search(self, query: str) -> list[RetrievalResult]:
        try:
            hits = self._bm25.search(query, top_k=self.bm25_top_k)
        except Exception as exc:
            logger.warning("BM25 search failed; degrading to vector only: %s", exc)
            return []

        return [
            RetrievalResult(
                doc_id=hit.doc_id,
                content=hit.content,
                diary_id=hit.diary_id,
                score=hit.bm25_score,
                chunk_index=hit.chunk_index,
                chunk_total=hit.chunk_total,
                date=hit.date,
                tags=hit.tags,
            )
            for hit in hits
        ]

    @staticmethod
    def _dedupe_by_diary(results: list[RetrievalResult]) -> list[RetrievalResult]:
        seen: set[str] = set()
        deduped: list[RetrievalResult] = []
        for result in results:
            key = result.diary_id or result.doc_id
            if key in seen:
                continue
            seen.add(key)
            deduped.append(result)
        return deduped

    @staticmethod
    def _log_trace(
        query: str,
        vector_count: int,
        bm25_count: int,
        fused_count: int,
        started: float,
    ) -> None:
        latency_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "rag.hybrid_retrieve query=%r vector_results_count=%d "
            "bm25_results_count=%d fused_results_count=%d latency_ms=%.2f",
            query[:100],
            vector_count,
            bm25_count,
            fused_count,
            latency_ms,
        )
