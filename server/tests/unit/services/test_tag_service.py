"""Unit tests for tag_service."""

from __future__ import annotations

import pytest

from app.services import tag_service
from app.shared.errors import TagConflictError, TagNotFoundError


def test_create_list_delete_tag(db_session) -> None:
    tag = tag_service.create_tag(db_session, name="工作", color="#FF0000")
    assert tag.id is not None

    tags = tag_service.list_tags(db_session)
    assert len(tags) == 1
    assert tag_service.get_tag(db_session, tag.id).name == "工作"

    with pytest.raises(TagConflictError):
        tag_service.create_tag(db_session, name="工作")

    tag_service.delete_tag(db_session, tag.id)
    with pytest.raises(TagNotFoundError):
        tag_service.get_tag(db_session, tag.id)
