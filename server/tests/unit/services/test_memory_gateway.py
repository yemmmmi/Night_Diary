"""Tests for the unified MemoryGateway."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.domain.memory.episodic import EpisodicMemory
from app.domain.memory.types import EmotionBaseline, EpisodicEntry, UserProfile
from app.infrastructure.database import create_db_engine, create_session_factory, init_db
from app.infrastructure.memory_repository import SqliteEpisodicMemoryStore
from app.services.memory_gateway import MemoryGateway, SessionType


@pytest.fixture
def _session_factory() -> sessionmaker[Session]:
    engine = create_db_engine("sqlite:///:memory:")
    init_db(engine)
    return create_session_factory(engine)


def _entry(
    *,
    importance: float = 0.8,
    timestamp: float | None = None,
    event: str = "测试事件",
    emotion: str = "neutral",
) -> EpisodicEntry:
    return EpisodicEntry(
        event=event,
        emotion=emotion,
        ai_suggestion="建议内容",
        user_feedback="none",
        timestamp=timestamp or time.time(),
        diary_ids=["1"],
        importance=importance,
        entry_id="",
    )


def _make_episodic(store: SqliteEpisodicMemoryStore) -> EpisodicMemory:
    return EpisodicMemory(store=store, user_id="default")


def _make_long_term() -> MagicMock:
    lt = MagicMock()
    lt.get_profile.return_value = UserProfile(
        preferred_response_style="warm",
        recurring_topics=["失眠", "加班"],
        emotion_baseline=EmotionBaseline(average_sentiment=0.5, volatility=0.2, dominant_emotion="neutral"),
    )
    return lt


def test_load_returns_episodic_and_profile(_session_factory: sessionmaker[Session]) -> None:
    store = SqliteEpisodicMemoryStore(_session_factory)
    episodic = _make_episodic(store)
    episodic.store(_entry(event="失眠", emotion="anxiety"))
    long_term = _make_long_term()

    gw = MemoryGateway(episodic=episodic, long_term=long_term)
    result = gw.load(query="睡眠", session_type=SessionType.DIARY)

    assert len(result.episodic_context) == 1
    assert result.episodic_context[0]["event"] == "失眠"
    assert result.profile_style == "warm"
    assert "失眠" in result.profile_topics


def test_load_with_empty_query_still_returns_entries(_session_factory: sessionmaker[Session]) -> None:
    store = SqliteEpisodicMemoryStore(_session_factory)
    episodic = _make_episodic(store)
    episodic.store(_entry(event="加班", importance=0.9))
    long_term = _make_long_term()

    gw = MemoryGateway(episodic=episodic, long_term=long_term)
    result = gw.load(query="", session_type=SessionType.CHAT)

    assert len(result.episodic_context) == 1
    assert result.episodic_context[0]["event"] == "加班"


def test_load_without_memory_returns_empty() -> None:
    gw = MemoryGateway()
    result = gw.load(query="test", session_type=SessionType.CHAT)
    assert result.episodic_context == []
    assert result.profile_style == ""


def test_persist_episodic_stores_and_triggers_promotion(_session_factory: sessionmaker[Session]) -> None:
    store = SqliteEpisodicMemoryStore(_session_factory)
    episodic = _make_episodic(store)
    long_term = _make_long_term()

    gw = MemoryGateway(episodic=episodic, long_term=long_term)
    stored = gw.persist_episodic(
        event="今天和好朋友吵架了",
        emotion="sad",
        ai_suggestion="理解你的感受",
        importance=0.7,
    )

    assert stored is True
    long_term.promote_from_episodic.assert_called_once()


def test_persist_episodic_without_long_term_still_stores(_session_factory: sessionmaker[Session]) -> None:
    store = SqliteEpisodicMemoryStore(_session_factory)
    episodic = _make_episodic(store)

    gw = MemoryGateway(episodic=episodic, long_term=None)
    stored = gw.persist_episodic(
        event="开心的一天",
        emotion="happy",
        importance=0.8,
    )
    assert stored is True


def test_persist_episodic_without_episodic_returns_false() -> None:
    gw = MemoryGateway(episodic=None)
    stored = gw.persist_episodic(event="test", emotion="neutral")
    assert stored is False


def test_persist_episodic_failure_does_not_raise() -> None:
    episodic = MagicMock()
    episodic.store.side_effect = RuntimeError("DB down")

    gw = MemoryGateway(episodic=episodic, long_term=None)
    stored = gw.persist_episodic(event="test", emotion="neutral")
    assert stored is False


def test_load_query_relevance_ranks_related_higher(_session_factory: sessionmaker[Session]) -> None:
    """The gateway passes query through to retrieve_relevant."""
    store = SqliteEpisodicMemoryStore(_session_factory)
    episodic = _make_episodic(store)
    now = time.time()
    episodic.store(_entry(event="加班", importance=0.7, timestamp=now))
    episodic.store(_entry(event="失眠", importance=0.6, timestamp=now))

    gw = MemoryGateway(episodic=episodic, long_term=None)
    result = gw.load(query="睡眠", session_type=SessionType.CHAT, top_k=2)

    assert result.episodic_context[0]["event"] == "失眠"
