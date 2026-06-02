"""Shared fixtures for skill unit tests."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.database import create_db_engine, create_session_factory, init_db
from app.infrastructure.skill_activation_tracer import SqliteSkillActivationTracer
from app.shared.tracing import InMemorySkillActivationTracer


@pytest.fixture
def activation_tracer() -> InMemorySkillActivationTracer:
    return InMemorySkillActivationTracer()


@pytest.fixture
def skill_session_factory() -> Generator[sessionmaker[Session], None, None]:
    engine = create_db_engine("sqlite:///:memory:")
    init_db(engine)
    yield create_session_factory(engine)


@pytest.fixture
def sqlite_activation_tracer(
    skill_session_factory: sessionmaker[Session],
) -> SqliteSkillActivationTracer:
    return SqliteSkillActivationTracer(skill_session_factory)
