"""Unit tests for StreamingSafetyGuard - the three-layer crisis safety net."""

import pytest

from app.shared.crisis_guard import CrisisGuard
from app.shared.emotion_estimator import EmotionEstimator
from app.shared.streaming_safety import StreamingSafetyGuard


def _make_guard() -> StreamingSafetyGuard:
    """Build a StreamingSafetyGuard with the real CrisisGuard + EmotionEstimator."""
    estimator = EmotionEstimator()
    crisis = CrisisGuard(emotion_estimator=estimator)
    return StreamingSafetyGuard(crisis_guard=crisis, buffer_size=50, window_size=80)


# 防线 1: should_stream_directly


def test_should_stream_directly_false_for_crisis_intent():
    """crisis_signal 意图必须走非流式。"""
    guard = _make_guard()
    assert guard.should_stream_directly("crisis_signal", "今天天气不错") is False


def test_should_stream_directly_false_when_crisis_guard_triggers():
    """非 crisis 意图但 CrisisGuard 命中（自伤关键词）也必须非流式。"""
    guard = _make_guard()
    assert guard.should_stream_directly("emotional_vent", "我不想活了") is False


def test_should_stream_directly_true_for_safe_input():
    """安全输入的普通意图可以走流式。"""
    guard = _make_guard()
    assert guard.should_stream_directly("casual_chat", "今天天气真好") is True


# 防线 2: 首段缓冲放行


@pytest.mark.asyncio
async def test_emotional_intent_buffers_before_flush():
    """emotional_vent 意图：首段缓冲到 buffer_size 后才放行。"""
    guard = _make_guard()  # buffer_size=50

    async def fake_stream():
        for char in "今天天气真的很不错，适合出门散步。" * 3:
            yield char

    output = []
    async for item in guard.filter_stream(fake_stream(), "emotional_vent"):
        if isinstance(item, str):
            output.append(item)

    result = "".join(output)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_emotional_intent_retract_on_crisis_in_buffer():
    """emotional_vent 意图：缓冲段检测到危机 -> RETRACT 事件。"""
    guard = _make_guard()  # buffer_size=50

    async def crisis_stream():
        for char in "今天天气真的很不错，适合出门散步的呀。" * 2:
            yield char
        yield "我不想活了"

    output = []
    async for item in guard.filter_stream(crisis_stream(), "emotional_vent"):
        output.append(item)

    retracts = [o for o in output if isinstance(o, dict) and o.get("retract")]
    assert len(retracts) == 1
    assert "安全" in retracts[0]["replacement"] or "陪" in retracts[0]["replacement"]


# 防线 3: 滑动窗口审核


@pytest.mark.asyncio
async def test_low_risk_intent_passes_through_directly():
    """casual_chat 低风险意图：直接透传，不缓冲。"""
    guard = _make_guard()

    async def fake_stream():
        for char in "你好世界":
            yield char

    output = []
    async for item in guard.filter_stream(fake_stream(), "casual_chat"):
        output.append(item)

    assert output == ["你", "好", "世", "界"]


@pytest.mark.asyncio
async def test_retrospective_query_passes_through_directly():
    """retrospective_query 低风险意图：直接透传。"""
    guard = _make_guard()

    async def fake_stream():
        yield "查一下上次的记录"

    output = []
    async for item in guard.filter_stream(fake_stream(), "retrospective_query"):
        output.append(item)

    assert output == ["查一下上次的记录"]


@pytest.mark.asyncio
async def test_short_reply_under_buffer_checked_at_end():
    """短回复（未达 buffer_size）在结束时检查一次。"""
    guard = _make_guard()  # buffer_size=50

    async def short_safe_stream():
        yield "好的，我明白了。"

    output = []
    async for item in guard.filter_stream(short_safe_stream(), "emotional_vent"):
        if isinstance(item, str):
            output.append(item)

    assert "".join(output) == "好的，我明白了。"


@pytest.mark.asyncio
async def test_short_crisis_reply_retracted():
    """短回复含危机内容：结束时检测到 -> RETRACT。"""
    guard = _make_guard()

    async def short_crisis_stream():
        yield "我不想活了"

    output = []
    async for item in guard.filter_stream(short_crisis_stream(), "emotional_vent"):
        output.append(item)

    retracts = [o for o in output if isinstance(o, dict) and o.get("retract")]
    assert len(retracts) == 1
