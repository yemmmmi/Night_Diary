"""Unit tests for WorkingMemory."""

from __future__ import annotations

from app.domain.memory.types import UserProfile
from app.domain.memory.working import WorkingMemory
from app.shared.token_utils import estimate_tokens


def test_load_context_initializes_state() -> None:
    wm = WorkingMemory()
    profile = UserProfile(recurring_topics=["失眠"])
    ctx = wm.load_context("d03", profile)

    assert ctx["diary_id"] == "d03"
    assert ctx["user_profile"]["recurring_topics"] == ["失眠"]
    assert ctx["turn"] == 0
    assert wm.is_active is True


def test_update_context_merges_turn_result() -> None:
    wm = WorkingMemory()
    ctx = wm.load_context("d03", UserProfile())
    wm.update_context(
        ctx,
        {
            "diary_content": "今天又睡不太好。",
            "retrieval_context": "Day1 你提到失眠。",
        },
    )

    active = wm.context
    assert active is not None
    assert active["diary_content"] == "今天又睡不太好。"
    assert active["retrieval_context"] == "Day1 你提到失眠。"
    assert active["turn"] == 1


def test_update_context_enforces_token_limit() -> None:
    wm = WorkingMemory()
    ctx = wm.load_context("d03", UserProfile())
    long_text = "失眠" * 5000

    wm.update_context(ctx, {"retrieval_context": long_text})
    active = wm.context
    assert active is not None
    assert estimate_tokens(active["retrieval_context"]) <= WorkingMemory.MAX_CONTEXT_TOKENS


def test_update_context_compresses_episodic_history() -> None:
    wm = WorkingMemory()
    ctx = wm.load_context("d03", UserProfile())
    wm.update_context(
        ctx,
        {
            "diary_content": "今天又失眠了。",
            "episodic_context": [
                {
                    "event_summary": "连续三天失眠",
                    "content": "连续三天失眠到凌晨两点，白天无法集中",
                },
                {"event_summary": "周末爬山", "content": "周末爬山心情不错，拍了好多照片"},
            ],
        },
    )
    active = wm.context
    assert active is not None
    assert active.get("compressed_history")
    assert "失眠" in active["compressed_history"]


def test_clear_resets_session() -> None:
    wm = WorkingMemory()
    wm.load_context("d03", UserProfile())
    wm.clear()
    assert wm.is_active is False
    assert wm.context is None
