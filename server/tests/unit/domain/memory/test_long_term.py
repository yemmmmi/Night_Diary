"""Unit tests for LongTermMemory."""

from __future__ import annotations

import statistics
import time

import pytest

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
            event_summary=event,
            emotion=emotion,
            reply_insight="建议",
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


# ── P0-B: emotion baseline activation from episodic mood_score ──


def _mood_entries(
    moods: list[float],
    emotions: list[str] | None = None,
    start_ts: float = 0.0,
) -> list[EpisodicEntry]:
    """Entries with explicit mood scores, one per day from ``start_ts``."""
    if emotions is None:
        emotions = ["悲伤", "疲惫", "孤独", "沮丧", "焦虑", "压力"] * 10
    return [
        EpisodicEntry(
            event_summary=f"事件{index}",
            emotion=emotions[index % len(emotions)],
            reply_insight="",
            timestamp=start_ts + index * 86400,
            mood_score=mood,
        )
        for index, mood in enumerate(moods)
    ]


def test_activates_emotion_baseline_from_mood_scores(
    profile_store: SqliteLongTermProfileStore,
) -> None:
    """average_sentiment/volatility roll from the mood_score window ([0,1] → [-1,1])."""
    memory = LongTermMemory(store=profile_store)
    moods = [0.2, 0.3, 0.25, 0.2]
    # Distinct emotions per day so the dominant-emotion rule stays quiet —
    # this test isolates the baseline activation path.
    emotions = ["悲伤", "疲惫", "孤独", "沮丧"]
    memory.promote_from_episodic("u1", _mood_entries(moods, emotions=emotions))

    baseline = memory.get_profile("u1").emotion_baseline
    sentiments = [m * 2.0 - 1.0 for m in moods]
    assert baseline.average_sentiment == pytest.approx(statistics.fmean(sentiments), abs=1e-3)
    assert baseline.volatility == pytest.approx(statistics.pstdev(sentiments), abs=1e-3)
    # dominant_emotion is owned by the consecutive-days rule, not the baseline.
    assert baseline.dominant_emotion == "neutral"


def test_baseline_requires_minimum_entries(profile_store: SqliteLongTermProfileStore) -> None:
    """Fewer than BASELINE_MIN_ENTRIES: an existing baseline must not be overwritten."""
    memory = LongTermMemory(store=profile_store)
    profile = UserProfile()
    profile.emotion_baseline.average_sentiment = 0.4
    memory.update_profile("u1", profile)

    memory.promote_from_episodic("u1", _mood_entries([0.1, 0.1]))  # 2 entries < 3

    assert memory.get_profile("u1").emotion_baseline.average_sentiment == 0.4


def test_baseline_skips_negligible_drift(profile_store: SqliteLongTermProfileStore) -> None:
    """Rolling mean within tolerance: no profile write (churn guard)."""
    memory = LongTermMemory(store=profile_store)
    profile = UserProfile()
    profile.emotion_baseline.average_sentiment = -0.29
    profile.emotion_baseline.volatility = 0.0
    memory.update_profile("u1", profile)

    # moods 0.35 → sentiment -0.3, volatility 0.0: average drift 0.01 < 0.02
    # tolerance, so the stored baseline must be left untouched.
    memory.promote_from_episodic("u1", _mood_entries([0.35, 0.35, 0.35]))

    baseline = memory.get_profile("u1").emotion_baseline
    assert baseline.average_sentiment == -0.29
    assert baseline.volatility == 0.0


def test_baseline_window_tracks_most_recent_entries(
    profile_store: SqliteLongTermProfileStore,
) -> None:
    """Only the most recent BASELINE_WINDOW_ENTRIES count, regardless of input order."""
    memory = LongTermMemory(store=profile_store)
    start = time.mktime(time.strptime("2026-06-01", "%Y-%m-%d"))
    moods = [0.9] * 10 + [0.1] * 10  # 10 old-high, 10 recent-low
    entries = _mood_entries(moods, start_ts=start)
    shuffled = list(reversed(entries))  # newest first — order must not matter

    memory.promote_from_episodic("u1", shuffled)

    baseline = memory.get_profile("u1").emotion_baseline
    window = moods[-14:]  # 4 old-high + 10 recent-low
    sentiments = [m * 2.0 - 1.0 for m in window]
    assert baseline.average_sentiment == pytest.approx(statistics.fmean(sentiments), abs=1e-3)
    # A whole-history mean would be 0.0; the windowed mean must be clearly negative.
    assert baseline.average_sentiment < -0.2
