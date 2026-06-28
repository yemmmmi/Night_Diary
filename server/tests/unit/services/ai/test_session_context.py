"""Tests for SessionContext — conversation-level state management."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.ai.session_context import (
    SessionContext,
    UsageAccumulator,
    clear_session,
    get_active_session_count,
    get_or_create_session,
)


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
