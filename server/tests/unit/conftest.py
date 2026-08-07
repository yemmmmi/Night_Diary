"""Shared fixtures for unit tests outside package-specific conftest files."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.database import create_db_engine, init_db
from tests.embedding_stub import patch_chroma_embedding_function


@pytest.fixture(autouse=True)
def _no_real_embedding_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests never load the real embedding model (heavy ML deps absent)."""
    patch_chroma_embedding_function(monkeypatch)


@pytest.fixture()
def db_session(tmp_path) -> Session:
    engine = create_db_engine(f"sqlite:///{tmp_path / 'unit.db'}")
    init_db(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
