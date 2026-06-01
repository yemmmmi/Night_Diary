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
