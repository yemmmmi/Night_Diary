"""Tests for the frozen memory block builder (D6)."""

from __future__ import annotations

from app.services.ai.memory_snapshot import (
    MAX_TOPICS,
    MEMORY_BLOCK_MAX_CHARS,
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