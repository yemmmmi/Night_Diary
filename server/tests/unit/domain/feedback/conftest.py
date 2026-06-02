"""Shared fixtures for feedback domain tests."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.domain.feedback.types import StylePreferenceRecord
from app.infrastructure.database import create_db_engine, create_session_factory, init_db
from app.infrastructure.feedback_repository import SqliteStylePreferenceStore


class InMemoryStylePreferenceStore:
    """Simple in-memory store for unit tests."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], StylePreferenceRecord] = {}

    def get_preferences(self, user_id: str) -> list[StylePreferenceRecord]:
        return [
            record
            for (uid, _), record in self._records.items()
            if uid == user_id
        ]

    def ensure_preferences(self, user_id: str, styles: list[str]) -> list[StylePreferenceRecord]:
        now = 0.0
        for style in styles:
            key = (user_id, style)
            if key not in self._records:
                self._records[key] = StylePreferenceRecord(style=style, updated_at=now)
        return self.get_preferences(user_id)

    def update_preference(self, user_id: str, style: str, *, alpha: float, beta: float) -> None:
        key = (user_id, style)
        current = self._records.get(key)
        if current is None:
            self._records[key] = StylePreferenceRecord(
                style=style,
                alpha=alpha,
                beta=beta,
            )
        else:
            self._records[key] = current.model_copy(
                update={"alpha": alpha, "beta": beta},
            )


@pytest.fixture
def memory_style_store() -> InMemoryStylePreferenceStore:
    return InMemoryStylePreferenceStore()


@pytest.fixture
def feedback_session_factory() -> Generator[sessionmaker[Session], None, None]:
    engine = create_db_engine("sqlite:///:memory:")
    init_db(engine)
    yield create_session_factory(engine)


@pytest.fixture
def sqlite_style_store(
    feedback_session_factory: sessionmaker[Session],
) -> SqliteStylePreferenceStore:
    return SqliteStylePreferenceStore(feedback_session_factory)
