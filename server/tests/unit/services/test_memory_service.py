"""Unit tests for the read-only memory_service (Memory Library)."""

from __future__ import annotations

import time

import pytest
from sqlalchemy.orm import sessionmaker

from app.domain.memory.types import (
    EmotionBaseline,
    EpisodicEntry,
    ImportantPerson,
    UserProfile,
)
from app.infrastructure.database import create_db_engine, init_db
from app.infrastructure.memory_repository import (
    SqliteEpisodicMemoryStore,
    SqliteLongTermProfileStore,
)
from app.services import card_service, memory_service


class _FakeContainer:
    """Minimal container exposing only what memory_service needs."""

    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory


@pytest.fixture()
def memory_ctx(tmp_path):
    engine = create_db_engine(f"sqlite:///{tmp_path / 'memory.db'}")
    init_db(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return _FakeContainer(factory)


def _card_entry(event: str, emotion: str, ts: float, *, entry_id: str) -> EpisodicEntry:
    return EpisodicEntry(
        event=event,
        emotion=emotion,
        ai_suggestion="",
        timestamp=ts,
        importance=0.7,
        diary_ids=[],
        entry_id=entry_id,
    )


def _diary_entry(event: str, ts: float, *, entry_id: str) -> EpisodicEntry:
    return EpisodicEntry(
        event=event,
        emotion="焦虑",
        ai_suggestion="试着深呼吸放松一下。",
        timestamp=ts,
        importance=0.8,
        diary_ids=["12"],
        entry_id=entry_id,
    )


def test_list_episodic_sorted_desc_with_source(memory_ctx) -> None:
    store = SqliteEpisodicMemoryStore(memory_ctx.session_factory)
    now = time.time()
    store.upsert_entry("default", _card_entry("散步", "平静", now - 100, entry_id="a"))
    store.upsert_entry("default", _diary_entry("失眠", now, entry_id="b"))

    entries = memory_service.list_episodic(memory_ctx)

    assert [e["entry_id"] for e in entries] == ["b", "a"]  # newest first
    assert entries[0]["source"] == "diary"
    assert entries[1]["source"] == "card"


def test_get_profile_none_when_absent(memory_ctx) -> None:
    assert memory_service.get_profile(memory_ctx) is None


def test_get_profile_returns_serialised_profile(memory_ctx) -> None:
    store = SqliteLongTermProfileStore(memory_ctx.session_factory)
    store.save_profile(
        "default",
        UserProfile(
            personality_tags=["内省", "敏感"],
            emotion_baseline=EmotionBaseline(
                average_sentiment=0.4, volatility=0.2, dominant_emotion="平静"
            ),
            important_people=[ImportantPerson(name="妈妈", relation="家人", sentiment=0.8)],
            recurring_topics=["工作", "睡眠"],
            preferred_response_style="empathetic",
        ),
    )

    profile = memory_service.get_profile(memory_ctx)

    assert profile is not None
    assert profile["personality_tags"] == ["内省", "敏感"]
    assert profile["emotion_baseline"]["dominant_emotion"] == "平静"
    assert profile["important_people"][0]["name"] == "妈妈"
    assert profile["recurring_topics"] == ["工作", "睡眠"]


def test_get_overview_counts(memory_ctx) -> None:
    store = SqliteEpisodicMemoryStore(memory_ctx.session_factory)
    now = time.time()
    store.upsert_entry("default", _card_entry("散步", "平静", now, entry_id="a"))
    store.upsert_entry("default", _diary_entry("失眠", now, entry_id="b"))

    with memory_ctx.session_factory() as session:
        card_service.create_card(session, emotion="开心", emotions=["开心"])

    overview = memory_service.get_overview(memory_ctx)

    assert overview["episodic_total"] == 2
    assert overview["episodic_from_cards"] == 1
    assert overview["episodic_from_diaries"] == 1
    assert overview["card_total"] == 1
    assert overview["profile_built"] is False
