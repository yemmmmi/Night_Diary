"""Unit tests for DomainKnowledgeStore."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.domain.knowledge.store import DomainKnowledgeStore


@pytest.fixture
def mock_collection() -> MagicMock:
    collection = MagicMock()
    collection.query.return_value = {
        "ids": [["doc-1", "doc-2"]],
        "documents": [["CBT tip", "Sleep hygiene tip"]],
        "metadatas": [
            [
                {"category": "cbt", "topic": "thought", "source": "manual"},
                {"category": "sleep_hygiene", "topic": "routine", "source": "manual"},
            ]
        ],
        "distances": [[0.15, 0.4]],
    }
    collection.count.return_value = 2
    return collection


@pytest.fixture
def store(mock_collection: MagicMock) -> DomainKnowledgeStore:
    client = MagicMock()
    client.get_collection.return_value = mock_collection
    client.get_or_create_collection.return_value = mock_collection
    return DomainKnowledgeStore(chroma_client=client)


def test_query_returns_knowledge_hits(store: DomainKnowledgeStore) -> None:
    hits = store.query("最近总是失眠怎么办")

    assert len(hits) == 2
    assert hits[0].content == "CBT tip"
    assert hits[0].category == "cbt"
    assert hits[0].reference_note == "【通用知识参考】"
    assert hits[0].doc_id == "doc-1"


def test_query_empty_text_returns_empty_list(store: DomainKnowledgeStore) -> None:
    assert store.query("   ") == []


def test_query_missing_collection_returns_empty_list() -> None:
    client = MagicMock()
    client.get_collection.side_effect = RuntimeError("missing")

    degraded = DomainKnowledgeStore(chroma_client=client)
    assert degraded.query("test") == []


def test_query_logs_trace(store: DomainKnowledgeStore, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("INFO"):
        store.query("失眠")

    assert any(
        "domain_knowledge.query" in record.message
        and "hit_count=2" in record.message
        and "latency_ms=" in record.message
        for record in caplog.records
    )


def test_add_returns_document_id(store: DomainKnowledgeStore, mock_collection: MagicMock) -> None:
    doc_id = store.add(
        "深呼吸有助于缓解焦虑",
        category="mindfulness",
        topic="breathing",
        source="seed",
        doc_id="seed-1",
    )

    assert doc_id == "seed-1"
    mock_collection.add.assert_called_once()


def test_delete_returns_true(store: DomainKnowledgeStore, mock_collection: MagicMock) -> None:
    assert store.delete("doc-1") is True
    mock_collection.delete.assert_called_once_with(ids=["doc-1"])


def test_get_stats_reports_count(store: DomainKnowledgeStore) -> None:
    assert store.get_stats() == {"initialized": True, "count": 2}
