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
        event_summary=event,
        emotion=emotion,
        reply_insight="建议内容",
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
        emotion_baseline=EmotionBaseline(
            average_sentiment=0.5, volatility=0.2, dominant_emotion="neutral"
        ),
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
    assert result.episodic_context[0]["event_summary"] == "失眠"
    assert result.profile_style == "warm"
    assert "失眠" in result.profile_topics


def test_load_with_empty_query_still_returns_entries(
    _session_factory: sessionmaker[Session],
) -> None:
    store = SqliteEpisodicMemoryStore(_session_factory)
    episodic = _make_episodic(store)
    episodic.store(_entry(event="加班", importance=0.9))
    long_term = _make_long_term()

    gw = MemoryGateway(episodic=episodic, long_term=long_term)
    result = gw.load(query="", session_type=SessionType.CHAT)

    assert len(result.episodic_context) == 1
    assert result.episodic_context[0]["event_summary"] == "加班"


def test_load_without_memory_returns_empty() -> None:
    gw = MemoryGateway()
    result = gw.load(query="test", session_type=SessionType.CHAT)
    assert result.episodic_context == []
    assert result.profile_style == ""


def test_persist_episodic_stores_and_triggers_promotion(
    _session_factory: sessionmaker[Session],
) -> None:
    store = SqliteEpisodicMemoryStore(_session_factory)
    episodic = _make_episodic(store)
    long_term = _make_long_term()

    gw = MemoryGateway(episodic=episodic, long_term=long_term)
    stored = gw.persist_episodic(
        event_summary="今天和好朋友吵架了",
        emotion="sad",
        reply_insight="理解你的感受",
        importance=0.7,
    )

    assert stored is True
    long_term.promote_from_episodic.assert_called_once()


def test_persist_episodic_without_long_term_still_stores(
    _session_factory: sessionmaker[Session],
) -> None:
    store = SqliteEpisodicMemoryStore(_session_factory)
    episodic = _make_episodic(store)

    gw = MemoryGateway(episodic=episodic, long_term=None)
    stored = gw.persist_episodic(
        event_summary="开心的一天",
        emotion="happy",
        importance=0.8,
    )
    assert stored is True


def test_persist_episodic_without_episodic_returns_false() -> None:
    gw = MemoryGateway(episodic=None)
    stored = gw.persist_episodic(event_summary="test", emotion="neutral")
    assert stored is False


def test_persist_episodic_failure_does_not_raise() -> None:
    episodic = MagicMock()
    episodic.store.side_effect = RuntimeError("DB down")

    gw = MemoryGateway(episodic=episodic, long_term=None)
    stored = gw.persist_episodic(event_summary="test", emotion="neutral")
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

    assert result.episodic_context[0]["event_summary"] == "失眠"


# ── P0-C: entity attach from the extraction sidecar ──


def _person_entity(name: str, relation: str = "", sentiment: float = 0.0) -> dict[str, object]:
    return {
        "name": name,
        "entity_type": "person",
        "relation": relation,
        "sentiment": sentiment,
    }


def test_attach_entities_finds_entry_by_diary_id(
    _session_factory: sessionmaker[Session],
) -> None:
    store = SqliteEpisodicMemoryStore(_session_factory)
    episodic = _make_episodic(store)
    episodic.store(_entry(event="和妈妈聊了很久", importance=0.8))
    long_term = _make_long_term()

    gw = MemoryGateway(episodic=episodic, long_term=long_term)
    attached = gw.attach_entities(
        user_id="default",
        source_ref="1",  # matches _entry's diary_ids=["1"]
        entities=[_person_entity("妈妈", relation="家人", sentiment=0.5)],
    )

    assert attached is True
    stored = episodic.get_all_entries_for_user("default")
    assert stored[0].entities[0]["name"] == "妈妈"
    long_term.promote_from_episodic.assert_called_once()


def test_attach_entities_matches_source_message_id(
    _session_factory: sessionmaker[Session],
) -> None:
    """Chat-path entries match by source_message_id (B3 provenance)."""
    store = SqliteEpisodicMemoryStore(_session_factory)
    episodic = _make_episodic(store)
    episodic.store(
        EpisodicEntry(
            event_summary="和小雨吵架了",
            emotion="sad",
            reply_insight="",
            timestamp=time.time(),
            importance=0.7,
            entry_id="",
            source_message_id="msg-42",
        )
    )

    gw = MemoryGateway(episodic=episodic, long_term=None)
    attached = gw.attach_entities(
        user_id="default",
        source_ref="msg-42",
        entities=[_person_entity("小雨", relation="恋人", sentiment=-0.2)],
    )

    assert attached is True
    stored = episodic.get_all_entries_for_user("default")
    assert stored[0].entities[0]["name"] == "小雨"


def test_attach_entities_dedupes_on_redispatch(
    _session_factory: sessionmaker[Session],
) -> None:
    """A re-dispatched sidecar job must not duplicate entities."""
    store = SqliteEpisodicMemoryStore(_session_factory)
    episodic = _make_episodic(store)
    episodic.store(_entry(event="和朋友吃饭", importance=0.8))

    gw = MemoryGateway(episodic=episodic, long_term=None)
    entities = [_person_entity("老王", relation="同事"), _person_entity("老王", relation="同事")]
    first = gw.attach_entities(user_id="default", source_ref="1", entities=entities)
    second = gw.attach_entities(user_id="default", source_ref="1", entities=entities)

    assert first is True
    assert second is True  # idempotent, not a failure
    stored = episodic.get_all_entries_for_user("default")
    names = [e["name"] for e in stored[0].entities]
    assert names == ["老王"]


def test_attach_entities_without_match_returns_false(
    _session_factory: sessionmaker[Session],
) -> None:
    store = SqliteEpisodicMemoryStore(_session_factory)
    episodic = _make_episodic(store)
    episodic.store(_entry(event="普通的一天", importance=0.8))

    gw = MemoryGateway(episodic=episodic, long_term=None)
    attached = gw.attach_entities(
        user_id="default",
        source_ref="999",  # no entry has this diary id
        entities=[_person_entity("妈妈")],
    )

    assert attached is False


def test_persist_atom_carries_entities_into_episodic(
    _session_factory: sessionmaker[Session],
) -> None:
    """The unified write path (atom → entry) must not drop atom.entities."""
    from app.domain.memory.atom import EntityRef, UnifiedMemoryAtom

    store = SqliteEpisodicMemoryStore(_session_factory)
    episodic = _make_episodic(store)

    gw = MemoryGateway(episodic=episodic, long_term=None)
    atom = UnifiedMemoryAtom(
        event_summary="陪儿子去公园",
        emotion="happy",
        reply_insight="",
        source="diary",
        importance=0.8,
        diary_id=7,
        entities=[EntityRef(name="儿子", entity_type="person", relation="家人", sentiment=0.6)],
    )
    assert gw.persist_atom(atom) is True

    stored = episodic.get_all_entries_for_user("default")
    assert stored[0].entities[0]["name"] == "儿子"
    assert stored[0].diary_ids == ["7"]


# ── P2-A: chat entries carry conversation_ids for sidecar joins ─────────


def test_persist_episodic_records_conversation_id(
    _session_factory: sessionmaker[Session],
) -> None:
    """Chat-path entries persist their conversation id (sidecar join key)."""
    store = SqliteEpisodicMemoryStore(_session_factory)
    episodic = _make_episodic(store)

    gw = MemoryGateway(episodic=episodic, long_term=None)
    assert (
        gw.persist_episodic(
            event_summary="和小雨聊了很久，心情好了一些",
            emotion="happy",
            importance=0.8,
            conversation_id="conv-7",
        )
        is True
    )

    stored = episodic.get_all_entries_for_user("default")
    assert stored[0].conversation_ids == ["conv-7"]


def test_attach_entities_matches_conversation_id(
    _session_factory: sessionmaker[Session],
) -> None:
    """The sidecar's source_ref=conversation_id now finds the entry (P2-A)."""
    store = SqliteEpisodicMemoryStore(_session_factory)
    episodic = _make_episodic(store)
    episodic.store(
        EpisodicEntry(
            event_summary="和小雨聊了很久，聊到很晚才睡下",
            emotion="neutral",
            reply_insight="",
            timestamp=time.time(),
            importance=0.7,
            entry_id="",
            conversation_ids=["conv-7"],
        )
    )

    gw = MemoryGateway(episodic=episodic, long_term=None)
    attached = gw.attach_entities(
        user_id="default",
        source_ref="conv-7",
        entities=[_person_entity("小雨", relation="朋友")],
    )

    assert attached is True
    stored = episodic.get_all_entries_for_user("default")
    assert stored[0].entities[0]["name"] == "小雨"
