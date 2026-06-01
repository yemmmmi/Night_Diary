"""Unit tests for DiaryCollectionManager."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.domain.rag.collections import COLLECTION_NAME, DiaryCollectionManager


@pytest.fixture
def mock_collection() -> MagicMock:
    collection = MagicMock()
    collection.count.return_value = 3
    return collection


@pytest.fixture
def manager(mock_collection: MagicMock) -> DiaryCollectionManager:
    client = MagicMock()
    client.get_or_create_collection.return_value = mock_collection
    client.get_collection.return_value = mock_collection
    return DiaryCollectionManager(chroma_client=client)


def test_upsert_diary_writes_chunks(manager: DiaryCollectionManager, mock_collection: MagicMock) -> None:
    content = "今天心情不错。" * 30
    written = manager.upsert_diary("entry-1", content, date="2025-06-01", tags="#心情")

    assert written >= 1
    mock_collection.upsert.assert_called_once()
    call_kwargs = mock_collection.upsert.call_args.kwargs
    assert len(call_kwargs["ids"]) == written
    assert call_kwargs["metadatas"][0]["diary_id"] == "entry-1"


def test_update_diary_deletes_then_upserts(
    manager: DiaryCollectionManager,
    mock_collection: MagicMock,
) -> None:
    manager.update_diary("entry-2", "更新后的日记内容。" * 20)

    mock_collection.delete.assert_called_once_with(where={"diary_id": "entry-2"})
    mock_collection.upsert.assert_called_once()


def test_delete_diary_by_metadata_filter(
    manager: DiaryCollectionManager,
    mock_collection: MagicMock,
) -> None:
    assert manager.delete_diary("entry-3") is True
    mock_collection.delete.assert_called_with(where={"diary_id": "entry-3"})


def test_upsert_empty_content_returns_zero(manager: DiaryCollectionManager) -> None:
    assert manager.upsert_diary("entry-4", "   ") == 0


def test_get_collection_uses_diary_chunks_name(
    manager: DiaryCollectionManager,
    mock_collection: MagicMock,
) -> None:
    client = manager._client
    assert client is not None
    manager.get_collection(create=True)
    client.get_or_create_collection.assert_called_once()
    assert client.get_or_create_collection.call_args.kwargs["name"] == COLLECTION_NAME
