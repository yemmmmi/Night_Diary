"""Unit tests for SqliteProfileChangeLogStore (P1-B audit persistence)."""

from __future__ import annotations

import json

from sqlalchemy import select

from app.infrastructure.memory_repository import SqliteProfileChangeLogStore
from app.infrastructure.models.profile_change_log import ProfileChangeLogRow


def test_record_change_persists_audit_row(memory_session_factory) -> None:
    store = SqliteProfileChangeLogStore(memory_session_factory)
    store.record_change(
        "u1",
        field="personality_tags",
        old_value=["乐观"],
        new_value=["乐观", "坚韧"],
        source="promotion",
        evidence=[{"date": "2026-06-03", "summary": "连续加班仍坚持跑步", "emotion": "疲惫"}],
    )

    with memory_session_factory() as session:
        row = session.scalars(select(ProfileChangeLogRow)).one()

    assert row.user_id == "u1"
    assert row.field == "personality_tags"
    assert json.loads(row.old_value) == ["乐观"]
    assert json.loads(row.new_value) == ["乐观", "坚韧"]
    assert row.source == "promotion"
    assert json.loads(row.evidence_json)[0]["date"] == "2026-06-03"
    assert row.created_at is not None


def test_record_change_handles_string_and_none_values(memory_session_factory) -> None:
    """Strings pass through unquoted; absent values stay NULL."""
    store = SqliteProfileChangeLogStore(memory_session_factory)
    store.record_change(
        "u1",
        field="preferred_response_style",
        old_value=None,
        new_value="pragmatic",
        source="manual",
    )

    with memory_session_factory() as session:
        row = session.scalars(select(ProfileChangeLogRow)).one()

    assert row.old_value is None
    assert row.new_value == "pragmatic"
    assert row.evidence_json is None
