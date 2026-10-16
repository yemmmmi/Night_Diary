"""Tests for the frozen memory block builder (D6) and fresh state block (D7)."""

from __future__ import annotations

from app.domain.memory.types import ShortTermState
from app.services.ai.memory_snapshot import (
    MAX_TOPICS,
    MEMORY_BLOCK_MAX_CHARS,
    build_fresh_state_block,
    build_frozen_memory_block,
)


def test_empty_profile_yields_empty_block() -> None:
    block = build_frozen_memory_block()
    assert block.empty
    assert block.text == ""
    assert block.budget.used_chars == 0
    assert not block.budget.over_budget


def test_block_includes_style_and_topics() -> None:
    block = build_frozen_memory_block(
        profile_style="温和", profile_topics=["失眠", "加班"]
    )
    assert not block.empty
    assert "温和" in block.text
    assert "失眠" in block.text
    assert block.budget.topic_count == 2
    assert block.budget.used_chars == len(block.text)
    assert not block.budget.over_budget
    assert not block.budget.consolidated


def test_topics_consolidated_when_too_many() -> None:
    topics = [f"主题{i}" for i in range(MAX_TOPICS + 5)]
    block = build_frozen_memory_block(profile_topics=topics)
    assert block.budget.topic_count == MAX_TOPICS
    assert block.budget.consolidated
    assert "主题0" in block.text
    assert f"主题{MAX_TOPICS}" not in block.text


def test_block_truncated_when_over_cap() -> None:
    block = build_frozen_memory_block(profile_style="x" * 2000, cap=100)
    assert block.budget.over_budget
    assert block.budget.consolidated
    assert len(block.text) <= 100
    assert block.text.endswith("…")


def test_blank_inputs_are_ignored() -> None:
    block = build_frozen_memory_block(profile_style="   ", profile_topics=["", "  "])
    assert block.empty


def test_block_includes_user_about_first() -> None:
    block = build_frozen_memory_block(
        user_about="我是夜班护士", profile_style="温和", profile_topics=["失眠"]
    )
    assert "我是夜班护士" in block.text
    # User-authored content is the highest-signal part → placed before the
    # system-inferred style/topics so it survives truncation.
    assert block.text.index("用户自述") < block.text.index("偏好风格")


def test_user_about_alone_is_enough() -> None:
    block = build_frozen_memory_block(user_about="我更喜欢被称呼「你」。")
    assert not block.empty
    assert "我更喜欢被称呼" in block.text
    assert block.budget.used_chars == len(block.text)


def test_about_prioritised_when_over_cap() -> None:
    block = build_frozen_memory_block(
        user_about="字" * 200, profile_style="x" * 200, cap=60
    )
    assert block.budget.over_budget
    assert block.budget.consolidated
    assert "用户自述" in block.text
    assert len(block.text) <= 60


def test_budget_to_dict_roundtrip() -> None:
    block = build_frozen_memory_block(profile_style="冷静")
    data = block.budget.to_dict()
    assert data["used_chars"] == len(block.text)
    assert data["cap_chars"] == MEMORY_BLOCK_MAX_CHARS
    assert data["topic_count"] == 0
    assert data["over_budget"] is False


# ---------------------------------------------------------------------------
# D7: fresh state block — turn-granular short_term_state in the volatile tail
# ---------------------------------------------------------------------------


def test_fresh_state_block_empty_for_none_state() -> None:
    assert build_fresh_state_block(None) == ""


def test_fresh_state_block_empty_when_nothing_to_say() -> None:
    # samples=0 + no modes → render() is empty → block must be skipped so the
    # user-prompt template stays byte-identical to the pre-D7 prompt.
    assert build_fresh_state_block(ShortTermState()) == ""


def test_fresh_state_block_renders_short_term_state() -> None:
    state = ShortTermState(
        recent_modes=["daily", "introspection"],
        composite_mood=0.30,
        samples=14,
        updated_date="2026-10-16",
    )
    block = build_fresh_state_block(state)
    assert "## 近期状态（每轮更新）" in block
    assert "- 近期状态：" in block
    assert "情绪偏低" in block
    # Leading/trailing newlines keep template formatting byte-identical when
    # the block is absent and cleanly sectioned when present.
    assert block.startswith("\n") and block.endswith("\n")


def test_fresh_state_block_caps_oversized_render() -> None:
    # render() aggregates (mode counts, mood mean) so it stays compact — force
    # the cap below the rendered length to exercise the truncation branch.
    state = ShortTermState(
        recent_modes=["daily"] * 100,
        composite_mood=0.30,
        samples=100,
    )
    block = build_fresh_state_block(state, cap=12)
    assert "…" in block
    assert len(block) < 60