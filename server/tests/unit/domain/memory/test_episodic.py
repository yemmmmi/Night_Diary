"""Unit tests for EpisodicMemory."""

from __future__ import annotations

import time

from app.domain.memory.episodic import EpisodicMemory
from app.domain.memory.types import EpisodicEntry
from app.infrastructure.memory_repository import SqliteEpisodicMemoryStore


def _entry(
    *,
    importance: float = 0.7,
    timestamp: float | None = None,
    event: str = "测试事件",
    emotion: str = "happy",
) -> EpisodicEntry:
    return EpisodicEntry(
        event=event,
        emotion=emotion,
        ai_suggestion="建议",
        user_feedback="none",
        timestamp=timestamp if timestamp is not None else time.time(),
        diary_ids=["d01"],
        importance=importance,
    )


def test_store_high_importance(episodic_store: SqliteEpisodicMemoryStore) -> None:
    memory = EpisodicMemory(store=episodic_store, user_id="u1")
    assert memory.store(_entry(importance=0.8)) is True
    assert memory.size == 1


def test_store_low_importance_skipped(episodic_store: SqliteEpisodicMemoryStore) -> None:
    memory = EpisodicMemory(store=episodic_store, user_id="u1")
    assert memory.store(_entry(importance=0.3)) is False
    assert memory.size == 0


def test_store_exact_threshold_skipped(episodic_store: SqliteEpisodicMemoryStore) -> None:
    memory = EpisodicMemory(store=episodic_store, user_id="u1")
    assert memory.store(_entry(importance=0.5)) is False


def test_retrieve_returns_top_k(episodic_store: SqliteEpisodicMemoryStore) -> None:
    memory = EpisodicMemory(store=episodic_store, user_id="u1")
    now = time.time()
    for index in range(8):
        memory.store(
            _entry(
                importance=0.6 + index * 0.05,
                timestamp=now - index * 3600,
                event=f"事件{index}",
            )
        )

    results = memory.retrieve_relevant(now=now)
    assert len(results) == 5


def test_retrieve_respects_decay(episodic_store: SqliteEpisodicMemoryStore) -> None:
    memory = EpisodicMemory(store=episodic_store, user_id="u1")
    now = time.time()
    memory.store(_entry(importance=0.6, timestamp=now, event="新事件"))
    memory.store(
        _entry(
            importance=0.7,
            timestamp=now - 30 * 24 * 3600,
            event="旧事件",
        )
    )

    results = memory.retrieve_relevant(now=now)
    assert results[0].event == "新事件"


def test_persistence_survives_restart(episodic_store: SqliteEpisodicMemoryStore) -> None:
    memory = EpisodicMemory(store=episodic_store, user_id="u1")
    entry = _entry(importance=0.8, event="失眠")
    memory.store(entry)

    reloaded = EpisodicMemory(store=episodic_store, user_id="u1")
    reloaded.load()
    hits = reloaded.retrieve_relevant(top_k=1)
    assert len(hits) == 1
    assert hits[0].event == "失眠"


def test_decay_purges_entries_below_threshold(episodic_store: SqliteEpisodicMemoryStore) -> None:
    memory = EpisodicMemory(store=episodic_store, user_id="u1")
    now = time.time()
    fourteen_days = 14 * 24 * 3600
    memory.store(_entry(importance=0.8, timestamp=now - fourteen_days, event="过期事件"))

    # store() triggers purge_stale(); 14-day decay drops effective score below 0.5.
    assert memory.size == 0


def test_evict_when_over_limit(episodic_store: SqliteEpisodicMemoryStore) -> None:
    memory = EpisodicMemory(store=episodic_store, user_id="u1", persist=False)
    now = time.time()
    for index in range(102):
        memory.store(
            _entry(
                importance=0.51 + index * 0.001,
                timestamp=now + index,
                event=f"事件{index}",
            )
        )

    assert memory.size == 100


def test_multiturn_insomnia_context_retained(episodic_store: SqliteEpisodicMemoryStore) -> None:
    """Simulate Day1 insomnia -> Day2 exercise -> Day3 recall."""
    memory = EpisodicMemory(store=episodic_store, user_id="default")
    day1 = time.mktime(time.strptime("2026-06-01", "%Y-%m-%d"))
    day2 = time.mktime(time.strptime("2026-06-02", "%Y-%m-%d"))
    day3 = time.mktime(time.strptime("2026-06-03", "%Y-%m-%d"))

    memory.store(
        _entry(
            importance=0.85,
            timestamp=day1,
            event="失眠",
            emotion="焦虑",
        )
    )
    memory.store(
        _entry(
            importance=0.75,
            timestamp=day2,
            event="晨跑",
            emotion="振奋",
        )
    )

    hits = memory.retrieve_relevant(query="睡眠", now=day3, top_k=2)
    assert any(hit.event == "失眠" for hit in hits)
