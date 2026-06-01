"""Unit tests for BM25Index."""

from __future__ import annotations

import time

from app.domain.rag.bm25 import BM25Index
from app.domain.rag.types import BM25Doc


def _doc(doc_id: str, content: str, diary_id: str = "1") -> BM25Doc:
    return BM25Doc(
        doc_id=doc_id,
        content=content,
        diary_id=diary_id,
        chunk_index=0,
        chunk_total=1,
    )


def test_build_and_search_returns_scored_results() -> None:
    index = BM25Index()
    index.build(
        [
            _doc("d1", "今天天气很好心情愉快"),
            _doc("d2", "工作压力很大需要放松"),
        ]
    )

    results = index.search("天气心情", top_k=2)
    assert len(results) <= 2
    assert all(result.bm25_score > 0 for result in results)


def test_empty_index_returns_empty() -> None:
    index = BM25Index()
    assert index.search("查询") == []


def test_results_sorted_by_score() -> None:
    index = BM25Index()
    index.build(
        [
            _doc("d1", "天气很好今天"),
            _doc("d2", "天气明天也不错"),
        ]
    )
    results = index.search("天气", top_k=10)
    if len(results) > 1:
        for i in range(len(results) - 1):
            assert results[i].bm25_score >= results[i + 1].bm25_score


def test_incremental_add_and_remove() -> None:
    index = BM25Index()
    index.add_document(_doc("d1", "失眠睡不着很难受"))
    index.add_document(_doc("d2", "运动之后睡眠改善"))

    assert index.doc_count == 2
    hits = index.search("失眠")
    assert hits and hits[0].doc_id == "d1"

    assert index.remove_document("d1") is True
    assert index.doc_count == 1
    assert index.search("失眠") == []


def test_add_document_replaces_existing_id() -> None:
    index = BM25Index()
    index.add_document(_doc("d1", "旧内容关于旅行"))
    index.add_document(_doc("d1", "新内容关于失眠"))

    assert index.doc_count == 1
    results = index.search("失眠")
    assert results and results[0].doc_id == "d1"


def test_incremental_add_faster_than_full_rebuild() -> None:
    """add_document() should be O(1)-ish vs rebuilding the full corpus."""
    index = BM25Index()
    base_docs = [
        _doc(f"doc-{i}", f"日记内容编号{i}包含一些中文关键词和情绪描述。")
        for i in range(500)
    ]
    index.build(base_docs)

    incremental_started = time.perf_counter()
    index.add_document(_doc("doc-new", "新增文档关于失眠和放松技巧"))
    incremental_ms = (time.perf_counter() - incremental_started) * 1000

    rebuild_index = BM25Index()
    rebuild_docs = [*base_docs, _doc("doc-new", "新增文档关于失眠和放松技巧")]
    rebuild_started = time.perf_counter()
    rebuild_index.build(rebuild_docs)
    rebuild_ms = (time.perf_counter() - rebuild_started) * 1000

    assert incremental_ms < 10.0
    assert incremental_ms < rebuild_ms * 0.5
