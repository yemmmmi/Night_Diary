"""Unit tests for diary_service."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from app.infrastructure.models.image_asset import ImageAssetRow
from app.services import diary_service
from app.shared.errors import DiaryNotFoundError, ValidationError


def _make_asset(db_session, *, user_id: str = "default") -> ImageAssetRow:
    row = ImageAssetRow(
        user_id=user_id,
        stored_filename="abc123.jpg",
        original_filename="海边.jpg",
        mime_type="image/jpeg",
        size_bytes=1024,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def test_create_entry_persists_and_syncs_chroma(db_session) -> None:
    manager = MagicMock()
    manager.update_diary.return_value = 2

    entry = diary_service.create_entry(
        db_session,
        user_id="default",
        content="今天天气不错。",
        collection_manager=manager,
    )

    assert entry.id is not None
    manager.update_diary.assert_called_once()


def test_create_entry_rejects_empty_content(db_session) -> None:
    with pytest.raises(ValidationError):
        diary_service.create_entry(db_session, user_id="default", content="   ")


def test_create_entry_uses_explicit_date(db_session) -> None:
    entry = diary_service.create_entry(
        db_session,
        user_id="default",
        content="指定日期",
        entry_date=date(2025, 6, 1),
    )
    assert entry.date == date(2025, 6, 1)


def test_get_recent_entries_shared_window(db_session) -> None:
    diary_service.create_entry(db_session, user_id="default", content="第一天")
    diary_service.create_entry(db_session, user_id="default", content="第二天")
    recent = diary_service.get_recent_entries(db_session, user_id="default", days=7, limit=5)
    assert len(recent) == 2


def test_delete_entry_removes_chroma_chunks(db_session) -> None:
    manager = MagicMock()
    entry = diary_service.create_entry(
        db_session,
        user_id="default",
        content="待删除",
        collection_manager=manager,
    )
    diary_service.delete_entry(db_session, entry.id, user_id="default", collection_manager=manager)
    manager.delete_diary.assert_called_with(str(entry.id))

    with pytest.raises(DiaryNotFoundError):
        diary_service.get_entry(db_session, entry.id, user_id="default")


def test_create_entry_persists_owned_image_assets(db_session) -> None:
    asset = _make_asset(db_session)
    entry = diary_service.create_entry(
        db_session,
        user_id="default",
        content="带图片的日记",
        image_asset_ids=[asset.id],
    )
    assert diary_service.parse_image_asset_ids(entry.image_assets_json) == [asset.id]


def test_create_entry_rejects_foreign_image_asset(db_session) -> None:
    other = _make_asset(db_session, user_id="someone-else")
    with pytest.raises(ValidationError):
        diary_service.create_entry(
            db_session,
            user_id="default",
            content="越权图片",
            image_asset_ids=[other.id],
        )


def test_update_entry_sets_and_clears_image_assets(db_session) -> None:
    asset = _make_asset(db_session)
    entry = diary_service.create_entry(db_session, user_id="default", content="初始")

    updated = diary_service.update_entry(
        db_session, entry.id, user_id="default", image_asset_ids=[asset.id]
    )
    assert diary_service.parse_image_asset_ids(updated.image_assets_json) == [asset.id]

    cleared = diary_service.update_entry(
        db_session, entry.id, user_id="default", image_asset_ids=[]
    )
    assert cleared.image_assets_json is None


def test_image_attachment_note_lists_filenames(db_session) -> None:
    asset = _make_asset(db_session)
    entry = diary_service.create_entry(
        db_session,
        user_id="default",
        content="带图片",
        image_asset_ids=[asset.id],
    )
    note = diary_service.image_attachment_note(db_session, entry, user_id="default")
    assert note == "附图片：海边.jpg"


def test_image_attachment_note_empty_without_assets(db_session) -> None:
    entry = diary_service.create_entry(db_session, user_id="default", content="无图片")
    assert diary_service.image_attachment_note(db_session, entry, user_id="default") == ""
