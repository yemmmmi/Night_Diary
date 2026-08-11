"""Tests for SessionContext — conversation-level state management."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.ai import session_context as sc
from app.services.ai.session_context import (
    MAX_SESSIONS,
    SessionContext,
    UsageAccumulator,
    clear_session,
    get_active_session_count,
    get_or_create_session,
    get_session_cache_stats,
)


@pytest.fixture(autouse=True)
def _reset_session_cache():
    """Ensure each test starts/ends with a clean module-level cache + counters."""
    sc._sessions.clear()
    sc._hits = 0
    sc._misses = 0
    yield
    sc._sessions.clear()
    sc._hits = 0
    sc._misses = 0


def test_usage_accumulator_adds_tokens() -> None:
    acc = UsageAccumulator()
    acc.add({"total_tokens_used": 100, "prompt_tokens": 60, "completion_tokens": 40})
    acc.add({"total_tokens_used": 50, "prompt_tokens": 30, "completion_tokens": 20})
    summary = acc.summary()
    assert summary["total_tokens"] == 150
    assert summary["prompt_tokens"] == 90
    assert summary["completion_tokens"] == 60
    assert summary["turn_count"] == 2


def test_session_context_add_turn_grows_history() -> None:
    ctx = SessionContext(conversation_id="test-1")
    ctx.add_turn("你好", "你好呀，今天怎么样？")
    history = ctx.get_history()
    assert "你好" in history
    assert "你好呀" in history


def test_session_context_empty_history() -> None:
    ctx = SessionContext(conversation_id="test-2")
    assert ctx.get_history() == "（暂无历史）"


def test_session_context_accumulate_usage() -> None:
    ctx = SessionContext(conversation_id="test-3")
    ctx.accumulate_usage({"total_tokens_used": 100})
    ctx.accumulate_usage({"total_tokens_used": 50})
    assert ctx.usage.total_tokens == 150
    assert ctx.usage.turn_count == 2


def test_get_or_create_session_caches() -> None:
    clear_session("cache-test")
    ctx1 = get_or_create_session("cache-test")
    ctx2 = get_or_create_session("cache-test")
    assert ctx1 is ctx2
    clear_session("cache-test")


def test_get_or_create_session_loads_profile() -> None:
    clear_session("profile-test")
    container = MagicMock()
    profile = MagicMock()
    profile.preferred_response_style = "warm"
    profile.recurring_topics = ["失眠", "加班"]
    container.long_term_memory = MagicMock()
    container.long_term_memory.get_profile.return_value = profile

    ctx = get_or_create_session("profile-test", container=container)
    assert ctx.profile_style == "warm"
    assert "失眠" in ctx.profile_topics
    clear_session("profile-test")


def test_clear_session_removes_context() -> None:
    get_or_create_session("clear-test")
    assert get_active_session_count() >= 1
    clear_session("clear-test")
    # Verify it's gone by checking a new one is created
    ctx = get_or_create_session("clear-test")
    assert ctx.usage.turn_count == 0
    clear_session("clear-test")


def test_session_context_profile_style_default_empty() -> None:
    ctx = SessionContext(conversation_id="test-4")
    assert ctx.profile_style == ""
    assert ctx.profile_topics == []


# ── LRU eviction + cache stats (P6 Task 2) ─────────────────────────────


def test_lru_evicts_oldest_when_max_exceeded() -> None:
    """Over MAX_SESSIONS should evict the least-recently-used session."""
    # Fill exactly up to the limit, in order conv_0 .. conv_{MAX-1}.
    for i in range(MAX_SESSIONS):
        get_or_create_session(f"conv_{i}")
    assert len(sc._sessions) == MAX_SESSIONS
    assert "conv_0" in sc._sessions  # oldest, least-recently-used so far

    # Adding one more should trigger eviction of the LRU entry (conv_0).
    get_or_create_session("conv_extra")

    assert len(sc._sessions) == MAX_SESSIONS  # size capped
    assert "conv_0" not in sc._sessions  # LRU evicted
    assert "conv_extra" in sc._sessions  # newest retained
    # The rest should still be present.
    for i in range(1, MAX_SESSIONS):
        assert f"conv_{i}" in sc._sessions


def test_lru_move_to_end_on_access() -> None:
    """Accessing a session should move it to the MRU end (not get evicted)."""
    # conv_old is created first → becomes the LRU candidate.
    get_or_create_session("conv_old")
    # Fill the rest so the cache is full.
    for i in range(MAX_SESSIONS - 1):
        get_or_create_session(f"conv_{i}")
    assert len(sc._sessions) == MAX_SESSIONS

    # Re-access conv_old → should be promoted to MRU (move_to_end).
    get_or_create_session("conv_old")

    # Insert a new session → evict the current LRU, which is now conv_0
    # (not conv_old, because conv_old was just touched).
    get_or_create_session("conv_new")

    assert "conv_old" in sc._sessions  # touched recently → retained
    assert "conv_0" not in sc._sessions  # now the LRU → evicted
    assert "conv_new" in sc._sessions


def test_session_cache_stats_reports_hit_rate() -> None:
    """get_session_cache_stats returns hit/miss counts and hit_rate."""
    # Miss: brand new session (create path).
    get_or_create_session("conv_1")
    # Hit: same session accessed again (L1 memory hit).
    get_or_create_session("conv_1")

    stats = get_session_cache_stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["size"] == 1
    assert stats["maxsize"] == MAX_SESSIONS
    assert stats["hit_rate"] == 0.5


def test_session_cache_stats_empty_hit_rate_zero() -> None:
    """With no traffic, hit_rate should be 0.0 (no division-by-zero)."""
    stats = get_session_cache_stats()
    assert stats["hits"] == 0
    assert stats["misses"] == 0
    assert stats["size"] == 0
    assert stats["maxsize"] == MAX_SESSIONS
    assert stats["hit_rate"] == 0.0
