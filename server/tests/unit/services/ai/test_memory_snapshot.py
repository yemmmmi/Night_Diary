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


def test_budget_to_dict_roundtrip() -> None:
    block = build_frozen_memory_block(profile_style="冷静")
    data = block.budget.to_dict()
    assert data["used_chars"] == len(block.text)
    assert data["cap_chars"] == MEMORY_BLOCK_MAX_CHARS
    assert data["topic_count"] == 0
    assert data["over_budget"] is False