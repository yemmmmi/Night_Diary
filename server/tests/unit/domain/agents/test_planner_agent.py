"""Unit tests for PlannerAgent and plan completeness logic."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.agents.plan_completeness import assess_plan_completeness
from app.domain.agents.planner_agent import PlannerAgent, PlannerInput


def test_completeness_both_present():
    """what 和 how 都有 -> complete。"""
    result = assess_plan_completeness("我想早睡", "11点前睡，睡前不看手机")
    assert result.is_complete is True
    # how 可有可无，但 what 必须有
    assert "what" not in result.missing_fields


def test_completeness_missing_how():
    """有 what 缺 how -> is_complete 仍为 True（what 足够生成 proposal，how 可由 Agent 建议）。"""
    result = assess_plan_completeness("我想养成早睡的习惯", "")
    # what 存在即可生成 proposal，how 缺失时 Agent 会提供建议
    assert "how" in result.missing_fields


def test_completeness_missing_what():
    """缺 what -> 不完整。"""
    result = assess_plan_completeness("", "")
    assert result.is_complete is False
    assert "what" in result.missing_fields


def test_completeness_extracts_what():
    """应能提取 what 字段供后续使用。"""
    result = assess_plan_completeness("我想坚持跑步", "")
    assert result.what is not None
    assert "跑步" in result.what or "跑步" in str(result.context)


@pytest.mark.asyncio
async def test_planner_emits_clarification_when_what_missing():
    """缺 what 时，PlannerAgent 应发 clarification_request 协议块。"""
    from app.shared.streaming_events import StreamingEventType
    from app.shared.trace_event_bus import get_event_bus

    trace_id = "test-planner-clarify-what"
    bus = get_event_bus()
    queue = await bus.subscribe(trace_id)

    planner = PlannerAgent(llm=MagicMock())
    inp = PlannerInput(
        user_input="嗯",  # 无目标信号词
        prior_context="",
        trace_id=trace_id,
        user_id="user-1",
        conversation_id="conv-1",
    )

    with patch("app.domain.agents.planner_agent.CrisisGuard") as mock_crisis_cls:
        mock_crisis_cls.return_value.detect.return_value = False
        await planner.run(inp)

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    await bus.unsubscribe(trace_id, queue)

    blocks = [e for e in events if e.get("type") == StreamingEventType.PROTOCOL_BLOCK]
    assert len(blocks) == 1
    assert blocks[0]["block"]["block_type"] == "clarification_request"
    assert "what" in blocks[0]["block"]["data"]["missing_fields"]


@pytest.mark.asyncio
async def test_planner_emits_proposal_when_complete():
    """what + how 都有，PlannerAgent 应发 plan_proposal。"""
    from app.shared.streaming_events import StreamingEventType
    from app.shared.trace_event_bus import get_event_bus

    trace_id = "test-planner-propose"
    bus = get_event_bus()
    queue = await bus.subscribe(trace_id)

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content=(
        '{"title":"早睡计划","motivation":"改善睡眠","tasks":[{"title":"11点前睡"}]}'
    )))

    planner = PlannerAgent(llm=mock_llm)
    inp = PlannerInput(
        user_input="我想早睡，每天11点前睡",  # 有目标 + 有方法
        prior_context="",
        trace_id=trace_id,
        user_id="user-1",
        conversation_id="conv-1",
    )

    with patch("app.domain.agents.planner_agent.CrisisGuard") as mock_crisis_cls:
        mock_crisis_cls.return_value.detect.return_value = False
        await planner.run(inp)

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    await bus.unsubscribe(trace_id, queue)

    blocks = [e for e in events if e.get("type") == StreamingEventType.PROTOCOL_BLOCK]
    assert len(blocks) == 1
    assert blocks[0]["block"]["block_type"] == "plan_proposal"
    assert blocks[0]["block"]["data"]["title"] == "早睡计划"


@pytest.mark.asyncio
async def test_planner_short_circuits_on_crisis():
    """危机信号应短路，不发协议块。"""
    from app.shared.streaming_events import StreamingEventType
    from app.shared.trace_event_bus import get_event_bus

    trace_id = "test-planner-crisis"
    bus = get_event_bus()
    queue = await bus.subscribe(trace_id)

    planner = PlannerAgent(llm=MagicMock())
    inp = PlannerInput(
        user_input="我不想活了，帮我规划",
        prior_context="",
        trace_id=trace_id,
        user_id="user-1",
        conversation_id="conv-1",
    )

    with patch("app.domain.agents.planner_agent.CrisisGuard") as mock_crisis_cls:
        mock_crisis_cls.return_value.detect.return_value = True
        mock_crisis_cls.return_value.safe_response = "安全模板"
        await planner.run(inp)

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    await bus.unsubscribe(trace_id, queue)

    # 危机短路：只应有 TEXT_DELTA（安全模板），无 PROTOCOL_BLOCK
    blocks = [e for e in events if e.get("type") == StreamingEventType.PROTOCOL_BLOCK]
    assert len(blocks) == 0


@pytest.mark.asyncio
async def test_planner_emits_reply_start_and_end():
    """PlannerAgent 应始终发 REPLY_START 和 REPLY_END。"""
    from app.shared.streaming_events import StreamingEventType
    from app.shared.trace_event_bus import get_event_bus

    trace_id = "test-planner-envelope"
    bus = get_event_bus()
    queue = await bus.subscribe(trace_id)

    planner = PlannerAgent(llm=MagicMock())
    inp = PlannerInput(
        user_input="嗯",
        prior_context="",
        trace_id=trace_id,
        user_id="user-1",
        conversation_id="conv-1",
    )

    with patch("app.domain.agents.planner_agent.CrisisGuard") as mock_crisis_cls:
        mock_crisis_cls.return_value.detect.return_value = False
        await planner.run(inp)

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    await bus.unsubscribe(trace_id, queue)

    types = [e["type"] for e in events]
    assert StreamingEventType.REPLY_START in types
    assert StreamingEventType.REPLY_END in types


@pytest.mark.asyncio
async def test_planner_emits_transition_text_before_proposal():
    """PlannerAgent 应在 plan_proposal 前发过渡语文本。"""
    from app.shared.streaming_events import StreamingEventType
    from app.shared.trace_event_bus import get_event_bus

    trace_id = "test-transition"
    bus = get_event_bus()
    queue = await bus.subscribe(trace_id)

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(
        return_value=MagicMock(
            content='{"title":"早睡计划","motivation":"改善睡眠","tasks":[{"title":"11点前睡"}]}'
        )
    )

    planner = PlannerAgent(llm=mock_llm)
    inp = PlannerInput(
        user_input="我想早睡，每天11点睡",
        prior_context="",
        trace_id=trace_id,
        user_id="user-1",
        conversation_id="conv-1",
    )

    with patch("app.domain.agents.planner_agent.CrisisGuard") as mock_crisis_cls:
        mock_crisis_cls.return_value.detect.return_value = False
        await planner.run(inp)

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    await bus.unsubscribe(trace_id, queue)

    deltas = [e for e in events if e.get("type") == StreamingEventType.TEXT_DELTA]
    blocks = [e for e in events if e.get("type") == StreamingEventType.PROTOCOL_BLOCK]

    # 应先有 TEXT_DELTA（过渡语），再有 PROTOCOL_BLOCK
    assert len(deltas) >= 1, f"Expected transition text deltas, got {len(deltas)}"
    assert len(blocks) == 1, f"Expected 1 protocol block, got {len(blocks)}"

    # 过渡语应包含"基于"或相关引导词
    transition_text = "".join(d.get("text", "") for d in deltas)
    assert "基于" in transition_text or "整理" in transition_text, (
        f"Transition text should contain guidance word, got: {transition_text}"
    )
