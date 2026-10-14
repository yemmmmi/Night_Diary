"""Tests for the entity-extraction sidecar's episodic attach path (P0-C)."""

from __future__ import annotations

import time

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.domain.agents.entity_extractor import _run_extraction_sync
from app.domain.memory.episodic import EpisodicMemory
from app.domain.memory.types import EpisodicEntry
from app.infrastructure.database import create_db_engine, create_session_factory, init_db
from app.infrastructure.memory_repository import SqliteEpisodicMemoryStore


@pytest.fixture
def session_factory() -> sessionmaker[Session]:
    engine = create_db_engine("sqlite:///:memory:")
    init_db(engine)
    return create_session_factory(engine)


def _seed_diary_entry(factory: sessionmaker[Session], *, diary_id: str = "42") -> None:
    """Persist the episodic entry the diary analysis flow would have written."""
    store = SqliteEpisodicMemoryStore(factory)
    episodic = EpisodicMemory(store=store, user_id="default")
    episodic.store(
        EpisodicEntry(
            event_summary="今天和妈妈大吵了一架",
            emotion="愤怒",
            reply_insight="",
            timestamp=time.time(),
            diary_ids=[diary_id],
            importance=0.8,
            entry_id="",
        )
    )


def test_extraction_attaches_entities_to_episodic_entry(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sidecar entities land on the diary's episodic entry even without Neo4j."""
    _seed_diary_entry(session_factory)
    monkeypatch.setattr(
        "app.infrastructure.entity_graph.is_neo4j_available", lambda: False
    )

    # Regex layer alone extracts 妈妈 (person) + 吵架-adjacent topics; the LLM
    # factory call inside fails open (llm=None) in the test environment.
    _run_extraction_sync(
        session_factory,
        "default",
        "42",
        "今天和妈妈大吵了一架，她又开始催婚，真的很累。",
        "diary",
    )

    store = SqliteEpisodicMemoryStore(session_factory)
    entries = store.load_entries("default")
    assert entries, "seeded episodic entry missing"
    names = {str(e.get("name")) for e in entries[0].entities}
    assert "妈妈" in names
    person = next(e for e in entries[0].entities if e.get("name") == "妈妈")
    assert person.get("entity_type") == "person"


def test_extraction_without_matching_entry_is_silent_noop(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No episodic entry for the source → nothing persisted, no crash."""
    monkeypatch.setattr(
        "app.infrastructure.entity_graph.is_neo4j_available", lambda: False
    )

    _run_extraction_sync(
        session_factory,
        "default",
        "404",
        "今天和妈妈大吵了一架。",
        "diary",
    )

    store = SqliteEpisodicMemoryStore(session_factory)
    assert store.load_entries("default") == []
