"""Shared fixtures for domain memory unit tests."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.database import create_db_engine, create_session_factory, init_db
from app.infrastructure.memory_repository import (
    SqliteEpisodicMemoryStore,
    SqliteLongTermProfileStore,
)


@pytest.fixture
def memory_session_factory() -> Generator[sessionmaker[Session], None, None]:
    engine = create_db_engine("sqlite:///:memory:")
    init_db(engine)
    yield create_session_factory(engine)


@pytest.fixture
def episodic_store(memory_session_factory: sessionmaker[Session]) -> SqliteEpisodicMemoryStore:
    return SqliteEpisodicMemoryStore(memory_session_factory)


@pytest.fixture
def profile_store(memory_session_factory: sessionmaker[Session]) -> SqliteLongTermProfileStore:
    return SqliteLongTermProfileStore(memory_session_factory)
