"""Shared fixtures for service-layer unit tests."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.database import Base, create_db_engine, init_db
from app.shared.llm_factory import StubLLMClient


@pytest.fixture()
def db_session(tmp_path) -> Session:
    engine = create_db_engine(f"sqlite:///{tmp_path / 'services.db'}")
    init_db(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def stub_llm() -> StubLLMClient:
    return StubLLMClient(reply="这是一条测试 AI 回应。")
