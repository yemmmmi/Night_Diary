"""Unit tests for diary_service."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from app.services import diary_service
from app.shared.errors import DiaryNotFoundError, ValidationError


def test_create_entry_persists_and_syncs_chroma(db_session) -> None:
    manager = MagicMock()
    manager.update_diary.return_value = 2

    entry = diary_service.create_entry(
        db_session,
        content="今天天气不错。",
        collection_manager=manager,
    )

    assert entry.id is not None
    manager.update_diary.assert_called_once()


def test_create_entry_rejects_empty_content(db_session) -> None:
    with pytest.raises(ValidationError):
        diary_service.create_entry(db_session, content="   ")


def test_create_entry_uses_explicit_date(db_session) -> None:
    entry = diary_service.create_entry(
        db_session,
        content="指定日期",
        entry_date=date(2025, 6, 1),
    )
    assert entry.date == date(2025, 6, 1)


def test_get_recent_entries_shared_window(db_session) -> None:
    diary_service.create_entry(db_session, content="第一天")
    diary_service.create_entry(db_session, content="第二天")
    recent = diary_service.get_recent_entries(db_session, days=7, limit=5)
    assert len(recent) == 2


def test_delete_entry_removes_chroma_chunks(db_session) -> None:
    manager = MagicMock()
    entry = diary_service.create_entry(
        db_session,
        content="待删除",
        collection_manager=manager,
    )
    diary_service.delete_entry(db_session, entry.id, collection_manager=manager)
    manager.delete_diary.assert_called_with(str(entry.id))

    with pytest.raises(DiaryNotFoundError):
        diary_service.get_entry(db_session, entry.id)
