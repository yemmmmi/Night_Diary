"""Unit tests for Reranker (lazy load, instance config, graceful degradation)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.domain.rag.reranker import Reranker
from app.domain.rag.types import RetrievalResult


def _candidates(n: int) -> list[RetrievalResult]:
    return [
        RetrievalResult(
            doc_id=f"d{i}",
            content=f"content {i}",
            diary_id=str(i),
            score=0.0,
        )
        for i in range(n)
    ]


def test_empty_candidates_returns_empty() -> None:
    reranker = Reranker(top_k=5, model_loader=lambda: MagicMock())
    assert reranker.rerank("query", []) == []


def test_rerank_orders_by_model_scores() -> None:
    model = MagicMock()
    model.predict.return_value = [0.1, 0.9, 0.5]
    reranker = Reranker(top_k=3, model_loader=lambda: model)

    result = reranker.rerank("query", _candidates(3))

    assert [r.doc_id for r in result] == ["d1", "d2", "d0"]
    assert result[0].rerank_score == 0.9
    assert result[0].score == 0.9


def test_rerank_respects_top_k() -> None:
    model = MagicMock()
    model.predict.return_value = [0.5, 0.4, 0.3, 0.2, 0.1]
    reranker = Reranker(top_k=2, model_loader=lambda: model)

    result = reranker.rerank("query", _candidates(5))

    assert len(result) == 2


def test_model_loaded_lazily_and_cached() -> None:
    model = MagicMock()
    model.predict.return_value = [0.5, 0.4]
    loader = MagicMock(return_value=model)
    reranker = Reranker(top_k=2, model_loader=loader)

    loader.assert_not_called()
    reranker.rerank("query", _candidates(2))
    reranker.rerank("query", _candidates(2))
    loader.assert_called_once()


def test_load_failure_degrades_to_fallback() -> None:
    def boom() -> object:
        raise RuntimeError("model not found")

    reranker = Reranker(top_k=3, model_loader=boom)
    candidates = _candidates(5)

    result = reranker.rerank("query", candidates)

    assert result == candidates[:3]
    assert all(r.rerank_score is None for r in result)


def test_load_failure_not_retried() -> None:
    loader = MagicMock(side_effect=RuntimeError("offline"))
    reranker = Reranker(top_k=2, model_loader=loader)

    reranker.rerank("query", _candidates(2))
    reranker.rerank("query", _candidates(2))

    loader.assert_called_once()


def test_predict_failure_degrades_to_fallback() -> None:
    model = MagicMock()
    model.predict.side_effect = ValueError("bad input")
    reranker = Reranker(top_k=2, model_loader=lambda: model)
    candidates = _candidates(4)

    result = reranker.rerank("query", candidates)

    assert result == candidates[:2]


def test_score_count_mismatch_logs_warning_and_pairs_min_length(
    caplog: pytest.LogCaptureFixture,
) -> None:
    model = MagicMock()
    model.predict.return_value = [0.9, 0.1]
    reranker = Reranker(top_k=5, model_loader=lambda: model)

    with caplog.at_level("WARNING"):
        result = reranker.rerank("query", _candidates(3))

    assert len(result) == 2
    assert any("score count mismatch" in record.message for record in caplog.records)


def test_no_global_env_mutation_on_construction(monkeypatch) -> None:
    import os

    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)

    Reranker(local_files_only=True, model_loader=lambda: MagicMock()).rerank(
        "query", _candidates(1)
    )

    assert "HF_HUB_OFFLINE" not in os.environ
    assert "TRANSFORMERS_OFFLINE" not in os.environ


def test_rerank_episodic_orders_by_relevance():
    """rerank_episodic 应按 query 相关性排序 entries。"""
    import time

    from app.domain.memory.types import EpisodicEntry

    reranker = Reranker()
    # Mock 模型避免加载真实 cross-encoder
    reranker._model = MagicMock()
    # predict 返回分数:第一条 0.1,第二条 0.9,第三条 0.5
    reranker._model.predict.return_value = [0.1, 0.9, 0.5]

    entries = [
        EpisodicEntry(event_summary="吃饭", emotion="n", timestamp=time.time(), importance=0.6),
        EpisodicEntry(event_summary="失眠", emotion="焦虑", timestamp=time.time(), importance=0.8),
        EpisodicEntry(event_summary="加班", emotion="累", timestamp=time.time(), importance=0.7),
    ]
    result = reranker.rerank_episodic("睡眠问题", entries)
    # 0.9 分(失眠)应排第一
    assert result[0].event_summary == "失眠"
    assert result[1].event_summary == "加班"  # 0.5
    assert result[2].event_summary == "吃饭"  # 0.1


def test_rerank_episodic_empty_input_returns_empty():
    """空列表输入应返回空列表。"""
    reranker = Reranker()
    assert reranker.rerank_episodic("query", []) == []


def test_rerank_episodic_single_entry_returns_same():
    """单条 entry 应原样返回。"""
    import time

    from app.domain.memory.types import EpisodicEntry

    reranker = Reranker()
    reranker._model = MagicMock()
    reranker._model.predict.return_value = [0.5]

    entry = EpisodicEntry(event_summary="测试", emotion="n", timestamp=time.time(), importance=0.6)
    result = reranker.rerank_episodic("query", [entry])
    assert len(result) == 1
    assert result[0].event_summary == "测试"


def test_rerank_episodic_uses_summary_and_tags():
    """rerank_episodic 应把 event_summary + tags 作为 content。"""
    import time

    from app.domain.memory.types import EpisodicEntry

    reranker = Reranker()
    reranker._model = MagicMock()
    reranker._model.predict.return_value = [0.5]

    entry = EpisodicEntry(
        event_summary="失眠",
        emotion="n",
        timestamp=time.time(),
        importance=0.6,
        tags=["睡眠", "健康"],
    )
    reranker.rerank_episodic("query", [entry])

    # 检查 predict 被调用时的 pairs 参数,content 应含 tags
    call_args = reranker._model.predict.call_args
    pairs = call_args[0][0]  # 第一个位置参数
    assert len(pairs) == 1
    query, content = pairs[0]
    assert query == "query"
    assert "失眠" in content
    assert "睡眠" in content or "健康" in content  # tags 拼入 content
