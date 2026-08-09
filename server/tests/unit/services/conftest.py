"""Shared fixtures for service-layer unit tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.database import create_db_engine, init_db
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


@pytest.fixture()
def stub_container() -> MagicMock:
    """A MagicMock container wired for safe-input paths in conversation AI.

    - ``retriever`` / ``episodic_memory`` / ``long_term_memory`` are ``None``
      so RAG, episodic, and profile-loading are skipped.
    - ``ensure_ai_stack`` is a no-op.
    - ``_llm_for_tier`` returns ``None`` so tool-building short-circuits.
    """
    container = MagicMock()
    container.ensure_ai_stack = MagicMock()
    container.retriever = None
    container.episodic_memory = None
    container.long_term_memory = None
    container._llm_for_tier = MagicMock(return_value=None)
    return container
