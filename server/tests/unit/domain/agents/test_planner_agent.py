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


# ── V3.2: 修改既有计划/任务提案 ────────────────────────────────


def _drain_blocks(queue):
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    return events


@pytest.mark.asyncio
async def test_planner_emits_plan_modify_when_existing():
    """有 current_plans_text 且用户指向修改既有计划 -> 发 plan_modify (adjust)。"""
    from app.shared.streaming_events import StreamingEventType
    from app.shared.trace_event_bus import get_event_bus

    trace_id = "test-plan-modify-adjust"
    bus = get_event_bus()
    queue = await bus.subscribe(trace_id)

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content=(
        '{"operation":"adjust","target":{"type":"plan","id":"abcd1234",'
        '"title":"早睡计划"},"changes":{"due_date":"2026-09-01"},"reason":"下周再调整"}'
    )))

    planner = PlannerAgent(llm=mock_llm)
    inp = PlannerInput(
        user_input="把早睡计划的截止日期改一下",
        prior_context="",
        trace_id=trace_id,
        user_id="user-1",
        conversation_id="conv-1",
        current_plans_text="- 计划[abcd1234]：《早睡计划》（未完成任务：11点前睡）",
    )

    with patch("app.domain.agents.planner_agent.CrisisGuard") as mock_crisis_cls:
        mock_crisis_cls.return_value.detect.return_value = False
        await planner.run(inp)

    events = _drain_blocks(queue)
    await bus.unsubscribe(trace_id, queue)

    blocks = [e for e in events if e.get("type") == StreamingEventType.PROTOCOL_BLOCK]
    modify = [b for b in blocks if b["block"]["block_type"] == "plan_modify"]
    assert len(modify) == 1, f"expected 1 plan_modify, got blocks={blocks}"
    data = modify[0]["block"]["data"]
    assert data["operation"] == "adjust"
    assert data["status"] == "awaiting_confirmation"
    assert data["target"]["title"] == "早睡计划"


@pytest.mark.asyncio
async def test_plan_modify_is_zero_write():
    """修改提案必须只读草案：responses 里绝无写库动作，状态恒为 awaiting_confirmation。"""
    from app.shared.streaming_events import StreamingEventType
    from app.shared.trace_event_bus import get_event_bus

    trace_id = "test-plan-modify-zw"
    bus = get_event_bus()
    queue = await bus.subscribe(trace_id)

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content=(
        '{"operation":"clean","target":{"type":"task","id":"t99",'
        '"title":"旧任务"},"changes":{},"reason":"不再需要"}'
    )))

    planner = PlannerAgent(llm=mock_llm)
    inp = PlannerInput(
        user_input="帮我把旧任务清掉吧",
        prior_context="",
        trace_id=trace_id,
        user_id="user-1",
        conversation_id="conv-1",
        current_plans_text="- 计划[abcd1234]：《早睡计划》（未完成任务：11点前睡、旧任务）",
    )

    with patch("app.domain.agents.planner_agent.CrisisGuard") as mock_crisis_cls:
        mock_crisis_cls.return_value.detect.return_value = False
        await planner.run(inp)

    events = _drain_blocks(queue)
    await bus.unsubscribe(trace_id, queue)

    blocks = [e for e in events if e.get("type") == StreamingEventType.PROTOCOL_BLOCK]
    modify = [b for b in blocks if b["block"]["block_type"] == "plan_modify"]
    assert len(modify) == 1
    # 零写权限：发出的是草案而非执行结果
    assert modify[0]["block"]["data"]["status"] == "awaiting_confirmation"


@pytest.mark.asyncio
async def test_plan_modify_falls_back_to_new_proposal():
    """LSM 判定为 none（用户其实想新建）-> 回落 plan_proposal。"""
    from app.shared.streaming_events import StreamingEventType
    from app.shared.trace_event_bus import get_event_bus

    trace_id = "test-plan-modify-none"
    bus = get_event_bus()
    queue = await bus.subscribe(trace_id)

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content=(
        '{"operation":"none"}'
    )))

    planner = PlannerAgent(llm=mock_llm)
    inp = PlannerInput(
        user_input="把计划调整成全早点睡",  # 含 adjust 分支信号，但 LS 判定 wanted none -> 回落新建
        prior_context="",
        trace_id=trace_id,
        user_id="user-1",
        conversation_id="conv-1",
        current_plans_text="- 计划[abcd1234]：《早睡计划》",
    )

    with patch("app.domain.agents.planner_agent.CrisisGuard") as mock_crisis_cls:
        mock_crisis_cls.return_value.detect.return_value = False
        await planner.run(inp)

    events = _drain_blocks(queue)
    await bus.unsubscribe(trace_id, queue)

    blocks = [e for e in events if e.get("type") == StreamingEventType.PROTOCOL_BLOCK]
    types = [b["block"]["block_type"] for b in blocks]
    # operation=none -> 打车回到 plan_proposal / clarification，绝不应出现 plan_modify
    assert "plan_modify" not in types


@pytest.mark.asyncio
async def test_plan_modify_no_current_plans_still_new():
    """没有 current_plans_text（默认规划）-> 即便带修改词，也不走 modify 分支（保持向后兼容）。"""
    from app.shared.streaming_events import StreamingEventType
    from app.shared.trace_event_bus import get_event_bus

    trace_id = "test-plan-modify-no-context"
    bus = get_event_bus()
    queue = await bus.subscribe(trace_id)

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content=(
        '{"title":"早睡计划","motivation":"x","tasks":[]}'
    )))

    planner = PlannerAgent(llm=mock_llm)
    inp = PlannerInput(
        user_input="把早睡计划的截止日期改一下",  # 含 modify 词，但无 current_plans_text
        prior_context="",
        trace_id=trace_id,
        user_id="user-1",
        conversation_id="conv-1",
        current_plans_text="",
    )

    with patch("app.domain.agents.planner_agent.CrisisGuard") as mock_crisis_cls:
        mock_crisis_cls.return_value.detect.return_value = False
        await planner.run(inp)

    events = _drain_blocks(queue)
    await bus.unsubscribe(trace_id, queue)

    blocks = [e for e in events if e.get("type") == StreamingEventType.PROTOCOL_BLOCK]
    types = [b["block"]["block_type"] for b in blocks]
    assert "plan_modify" not in types
