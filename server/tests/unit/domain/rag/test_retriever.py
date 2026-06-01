"""Unit tests for HybridRetriever and RRF fusion."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.domain.rag.retriever import HybridRetriever, reciprocal_rank_fusion
from app.domain.rag.types import RetrievalResult, SearchResult


def _result(doc_id: str, diary_id: str, score: float = 0.0) -> RetrievalResult:
    return RetrievalResult(doc_id=doc_id, content=doc_id, diary_id=diary_id, score=score)


def _vector_payload() -> dict:
    return {
        "ids": [["diary_1_chunk_0", "diary_2_chunk_0"]],
        "documents": [["今天很开心", "工作压力大"]],
        "metadatas": [
            [
                {"diary_id": "1", "date": "2025-01-01", "chunk_index": 0, "chunk_total": 1},
                {"diary_id": "2", "date": "2025-01-02", "chunk_index": 0, "chunk_total": 1},
            ]
        ],
        "distances": [[0.2, 0.6]],
    }


@pytest.fixture
def collection() -> MagicMock:
    col = MagicMock()
    col.count.return_value = 2
    col.query.return_value = _vector_payload()
    return col


@pytest.fixture
def collection_manager(collection: MagicMock) -> MagicMock:
    manager = MagicMock()
    manager.get_collection.return_value = collection
    return manager


@pytest.fixture
def bm25_index() -> MagicMock:
    index = MagicMock()
    index.search.return_value = [
        SearchResult(doc_id="diary_2_chunk_0", content="工作压力大", diary_id="2", bm25_score=3.1),
        SearchResult(doc_id="diary_3_chunk_0", content="周末旅行", diary_id="3", bm25_score=1.2),
    ]
    return index


def test_rrf_no_duplicate_doc_ids() -> None:
    list_a = [_result("a", "1"), _result("b", "2")]
    list_b = [_result("b", "2"), _result("c", "3")]

    fused = reciprocal_rank_fusion([list_a, list_b])

    doc_ids = [r.doc_id for r in fused]
    assert sorted(doc_ids) == ["a", "b", "c"]
    assert len(doc_ids) == len(set(doc_ids))


def test_rrf_sorted_descending() -> None:
    list_a = [_result("a", "1"), _result("b", "2")]
    list_b = [_result("b", "2"), _result("a", "1")]

    fused = reciprocal_rank_fusion([list_a, list_b])

    scores = [r.score for r in fused]
    assert scores == sorted(scores, reverse=True)


def test_retrieve_fuses_vector_and_bm25(
    collection_manager: MagicMock,
    bm25_index: MagicMock,
) -> None:
    retriever = HybridRetriever(collection_manager, bm25_index, final_top_k=5)

    results = retriever.retrieve("压力")

    diary_ids = [r.diary_id for r in results]
    assert set(diary_ids) == {"1", "2", "3"}
    assert len(diary_ids) == len(set(diary_ids))


def test_retrieve_dedupes_by_diary_id(
    collection_manager: MagicMock,
    bm25_index: MagicMock,
) -> None:
    retriever = HybridRetriever(collection_manager, bm25_index, final_top_k=10)

    results = retriever.retrieve("压力")

    assert len([r for r in results if r.diary_id == "2"]) == 1


def test_retrieve_empty_query_returns_empty(
    collection_manager: MagicMock,
    bm25_index: MagicMock,
) -> None:
    retriever = HybridRetriever(collection_manager, bm25_index)
    assert retriever.retrieve("   ") == []


def test_retrieve_degrades_when_vector_fails(
    collection_manager: MagicMock,
    collection: MagicMock,
    bm25_index: MagicMock,
) -> None:
    collection.query.side_effect = RuntimeError("chroma down")
    retriever = HybridRetriever(collection_manager, bm25_index)

    results = retriever.retrieve("压力")

    assert {r.diary_id for r in results} == {"2", "3"}


def test_retrieve_degrades_when_bm25_fails(
    collection_manager: MagicMock,
    bm25_index: MagicMock,
) -> None:
    bm25_index.search.side_effect = RuntimeError("bm25 down")
    retriever = HybridRetriever(collection_manager, bm25_index)

    results = retriever.retrieve("压力")

    assert {r.diary_id for r in results} == {"1", "2"}


def test_retrieve_invokes_reranker(
    collection_manager: MagicMock,
    bm25_index: MagicMock,
) -> None:
    reranker = MagicMock()
    reranker.rerank.side_effect = lambda _query, candidates: candidates
    retriever = HybridRetriever(collection_manager, bm25_index, reranker=reranker)

    retriever.retrieve("压力")

    reranker.rerank.assert_called_once()


def test_retrieve_emits_trace_log(
    collection_manager: MagicMock,
    bm25_index: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    retriever = HybridRetriever(collection_manager, bm25_index)

    with caplog.at_level("INFO"):
        retriever.retrieve("压力")

    assert any(
        "rag.hybrid_retrieve" in record.message
        and "vector_results_count=2" in record.message
        and "bm25_results_count=2" in record.message
        and "fused_results_count=" in record.message
        and "latency_ms=" in record.message
        for record in caplog.records
    )
