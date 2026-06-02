"""Unit tests for LongTermMemory."""

from __future__ import annotations

import time

from app.domain.memory.long_term import LongTermMemory
from app.domain.memory.types import EpisodicEntry, UserProfile
from app.infrastructure.memory_repository import SqliteLongTermProfileStore


def test_get_profile_returns_default(profile_store: SqliteLongTermProfileStore) -> None:
    memory = LongTermMemory(store=profile_store)
    assert memory.get_profile("missing") == UserProfile()


def test_update_and_reload_profile(profile_store: SqliteLongTermProfileStore) -> None:
    memory = LongTermMemory(store=profile_store)
    profile = UserProfile(personality_tags=["乐观"], recurring_topics=["运动"])
    memory.update_profile("u1", profile)

    reloaded = LongTermMemory(store=profile_store)
    saved = reloaded.get_profile("u1")
    assert saved.personality_tags == ["乐观"]
    assert saved.recurring_topics == ["运动"]


def _entries_for_days(emotion: str, event: str, days: int, start_ts: float) -> list[EpisodicEntry]:
    return [
        EpisodicEntry(
            event=event,
            emotion=emotion,
            ai_suggestion="建议",
            timestamp=start_ts + index * 86400,
            diary_ids=[f"d{index + 1}"],
            importance=0.7,
        )
        for index in range(days)
    ]


def test_promotes_topic_after_three_consecutive_days(
    profile_store: SqliteLongTermProfileStore,
) -> None:
    memory = LongTermMemory(store=profile_store)
    start = time.mktime(time.strptime("2026-06-01", "%Y-%m-%d"))
    entries = _entries_for_days("焦虑", "工作压力大", 3, start)
    memory.promote_from_episodic("u1", entries)

    profile = memory.get_profile("u1")
    assert "工作压力大" in profile.recurring_topics


def test_does_not_promote_with_only_two_days(profile_store: SqliteLongTermProfileStore) -> None:
    memory = LongTermMemory(store=profile_store)
    start = time.mktime(time.strptime("2026-06-01", "%Y-%m-%d"))
    entries = _entries_for_days("焦虑", "短期事件", 2, start)
    memory.promote_from_episodic("u1", entries)

    profile = memory.get_profile("u1")
    assert profile.recurring_topics == []


def test_promotes_emotion_to_dominant(profile_store: SqliteLongTermProfileStore) -> None:
    memory = LongTermMemory(store=profile_store)
    start = time.mktime(time.strptime("2026-06-01", "%Y-%m-%d"))
    entries = _entries_for_days("焦虑", "不同事件", 3, start)
    memory.promote_from_episodic("u1", entries)

    profile = memory.get_profile("u1")
    assert profile.emotion_baseline.dominant_emotion == "焦虑"


def test_find_consecutive_items() -> None:
    memory = LongTermMemory()
    daily_items = {
        "2024-01-01": {"work", "sleep"},
        "2024-01-02": {"work", "exercise"},
        "2024-01-03": {"work", "reading"},
    }
    result = memory._find_consecutive_items(daily_items, threshold=3)
    assert "work" in result
    assert "sleep" not in result
