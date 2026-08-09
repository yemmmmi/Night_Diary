"""Tests for ConversationLoop — the Agentic Loop engine."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.agents.types import ChatIntentResult
from app.services.ai.conversation_loop import (
    _needs_tool_call,
    run_conversation_loop,
    run_conversation_loop_streaming,
)
from app.services.ai.session_context import clear_session
from app.shared.llm_factory import StubLLMClient
from app.shared.streaming_events import StreamingEventType
from app.shared.tool_protocol import ToolCallResult, parse_text_tag_calls
from app.shared.trace_event_bus import get_event_bus


def test_parse_tool_calls_extracts_name_and_args() -> None:
    text = '我来查一下 <tool>search_diary</tool> <args>{"query": "失眠"}</args>'
    calls = parse_text_tag_calls(text)
    assert len(calls) == 1
    assert calls[0].name == "search_diary"
    assert calls[0].args == {"query": "失眠"}


def test_parse_tool_calls_no_calls() -> None:
    text = "今天天气不错，去公园散步了。"
    assert parse_text_tag_calls(text) == []


def test_parse_tool_calls_invalid_json_fallback() -> None:
    text = "<tool>search_diary</tool> <args>失眠记录</args>"
    calls = parse_text_tag_calls(text)
    assert len(calls) == 1
    assert calls[0].args == {"query": "失眠记录"}


def test_needs_tool_call_with_temporal_keyword() -> None:
    assert _needs_tool_call("昨天和小王吵架了") is True
    assert _needs_tool_call("上次说的那件事") is True


def test_needs_tool_call_without_temporal_keyword() -> None:
    assert _needs_tool_call("今天好累") is False
    assert _needs_tool_call("你好") is False


def test_run_conversation_loop_no_llm_returns_fallback() -> None:
    """When LLM is unavailable, the loop returns fallback immediately."""
    clear_session("no-llm-test")
    container = MagicMock()
    container.long_term_memory = None
    container._llm_for_tier.return_value = None

    result = run_conversation_loop(
        MagicMock(),
        container,
        conversation_id="no-llm-test",
        content="你好",
        pinned_diaries_text="（无）",
        retrieved_diaries_text="（无）",
        episodic_text="（无）",
        memory_ids=[],
        tools=None,
        use_graph=False,
    )

    assert result.stop_reason == "no_llm"
    assert result.reply_text  # Should be fallback text
    clear_session("no-llm-test")


def test_run_conversation_loop_simple_reply() -> None:
    """A normal message without temporal keywords should complete in 1 iteration."""
    clear_session("simple-test")
    fake_response = MagicMock()
    fake_response.content = "你好呀，今天怎么样？"
    fake_response.response_metadata = {
        "token_usage": {"total_tokens": 70, "prompt_tokens": 50, "completion_tokens": 20}
    }

    llm = MagicMock()
    llm.invoke.return_value = fake_response

    container = MagicMock()
    container.long_term_memory = None
    container._llm_for_tier.return_value = llm

    result = run_conversation_loop(
        MagicMock(),
        container,
        conversation_id="simple-test",
        content="你好",
        pinned_diaries_text="（无）",
        retrieved_diaries_text="（无）",
        episodic_text="（无）",
        memory_ids=[],
        tools=None,
        use_graph=False,
    )

    assert result.stop_reason == "completed"
    assert "你好" in result.reply_text
    assert result.tool_calls_made == []
    assert result.token_info.get("total_tokens_used", 0) == 70
    clear_session("simple-test")


def test_run_conversation_loop_tool_call_executes() -> None:
    """When the LLM emits a tool call, it should be executed and re-queried."""
    clear_session("tool-test")

    # First response: LLM calls a tool
    tool_response = MagicMock()
    tool_response.content = '<tool>search_diary</tool> <args>{"query": "失眠"}</args>'
    tool_response.response_metadata = {
        "token_usage": {"total_tokens": 60, "prompt_tokens": 50, "completion_tokens": 10}
    }

    # Second response: LLM gives final answer after seeing tool results
    final_response = MagicMock()
    final_response.content = "你之前提到过失眠的问题..."
    final_response.response_metadata = {
        "token_usage": {"total_tokens": 110, "prompt_tokens": 80, "completion_tokens": 30}
    }

    llm = MagicMock()
    llm.invoke.side_effect = [tool_response, final_response]
    # Ensure fallback text-tag path (MagicMock auto-creates bind_tools)
    llm.bind_tools = None

    container = MagicMock()
    container.long_term_memory = None
    container._llm_for_tier.return_value = llm

    # Mock tool
    search_tool = MagicMock(return_value="找到3条相关日记：...")
    tools = {"search_diary": search_tool}

    result = run_conversation_loop(
        MagicMock(),
        container,
        conversation_id="tool-test",
        content="昨天又失眠了，和上次一样",
        pinned_diaries_text="（无）",
        retrieved_diaries_text="（无）",
        episodic_text="（无）",
        memory_ids=[],
        tools=tools,
        use_graph=False,
    )

    assert result.stop_reason == "completed"
    assert "search_diary" in result.tool_calls_made
    assert search_tool.called
    assert "失眠" in result.reply_text
    # Token usage should be accumulated across both iterations
    assert result.token_info.get("total_tokens_used", 0) == 170
    clear_session("tool-test")


# ── Citation tracking tests (result integration enhancement) ──


def test_citations_tracked_for_context_sources(db_session) -> None:
    """Citations are tracked for pinned diaries, retrieved diaries, and episodic memories."""
    container = MagicMock()
    container._llm_for_tier = MagicMock(return_value=StubLLMClient(reply="好的回复"))
    container.ensure_ai_stack = MagicMock()
    container.session_factory = None

    result = run_conversation_loop(
        db_session,
        container,
        conversation_id="citation-test",
        content="今天怎么样",
        pinned_diaries_text="置顶日记内容：昨天很开心",
        retrieved_diaries_text="检索日记内容：上周去了公园",
        episodic_text="情景记忆：之前聊过工作压力",
        memory_ids=[],
        use_graph=False,
    )

    # Should have 3 citations: pinned diary, retrieved diary, episodic memory
    assert len(result.citations) >= 3
    source_types = [c.source_type for c in result.citations]
    assert "diary" in source_types
    assert "memory" in source_types

    # The reply should contain a "参考来源" section
    assert "参考来源" in result.reply_text
    clear_session("citation-test")


def test_citations_tracked_for_tool_calls(db_session) -> None:
    """Tool call results are tracked as citations."""
    search_tool = MagicMock(return_value="找到3条相关日记")
    tools = {"search_diary": search_tool}

    container = MagicMock()
    container._llm_for_tier = MagicMock(
        return_value=StubLLMClient(reply='<tool>search_diary</tool><args>{"query": "工作"}</args>')
    )
    container.ensure_ai_stack = MagicMock()

    with patch("app.services.ai.conversation_loop.parse_text_tag_calls") as mock_parse:
        mock_parse.side_effect = [
            [ToolCallResult(name="search_diary", args={"query": "工作"})],
            [],
        ]
        result = run_conversation_loop(
            db_session,
            container,
            conversation_id="tool-citation-test",
            content="查一下工作的日记",
            pinned_diaries_text="",
            retrieved_diaries_text="",
            episodic_text="",
            memory_ids=[],
            tools=tools,
            use_graph=False,
            intent_result=ChatIntentResult(
                intent_category="retrospective_query",
                confidence=0.9,
                need_retrieval=False,
                need_tools=["search_diary"],
                need_entity_query=False,
                tier="medium",
                max_iterations=2,
            ),
        )

    # Should have at least 1 tool citation
    tool_citations = [c for c in result.citations if c.source_type == "tool"]
    assert len(tool_citations) >= 1
    assert tool_citations[0].source_name == "search_diary"
    clear_session("tool-citation-test")


def test_no_citations_when_no_context(db_session) -> None:
    """No citations when all context sources are empty."""
    container = MagicMock()
    container._llm_for_tier = MagicMock(return_value=StubLLMClient(reply="简单回复"))
    container.ensure_ai_stack = MagicMock()

    result = run_conversation_loop(
        db_session,
        container,
        conversation_id="no-citation-test",
        content="你好",
        pinned_diaries_text="",
        retrieved_diaries_text="",
        episodic_text="",
        memory_ids=[],
        use_graph=False,
    )

    # No citations, no "参考来源" section
    assert len(result.citations) == 0
    assert "参考来源" not in result.reply_text
    clear_session("no-citation-test")


# ── Streaming variant tests (V3 P0) ──


class _StreamingStubLLM:
    """Stub LLM supporting both invoke (tool rounds) and astream (final reply)."""

    def __init__(self, *, tokens: list[str], invoke_reply: str = "") -> None:
        self._tokens = list(tokens)
        self._invoke_reply = invoke_reply
        self.astream_prompts: list[str] = []
        self.invoke_prompts: list[str] = []

    def invoke(self, prompt: str) -> Any:
        self.invoke_prompts.append(prompt)
        return SimpleNamespace(
            content=self._invoke_reply,
            response_metadata={"token_usage": {"total_tokens": 10, "completion_tokens": 5}},
        )

    async def ainvoke(self, prompt: str) -> Any:
        return self.invoke(prompt)

    async def astream(self, prompt: str):  # type: ignore[override]
        self.astream_prompts.append(prompt)
        for token in self._tokens:
            yield token


@pytest.mark.asyncio
async def test_run_conversation_loop_streaming_yields_tokens() -> None:
    """流式 loop 应逐 token yield 字符串。"""
    clear_session("stream-tokens-test")
    llm = _StreamingStubLLM(tokens=["你", "好", "呀"])

    container = MagicMock()
    container.long_term_memory = None
    container._llm_for_tier.return_value = llm

    collected: list[str] = []
    async for item in run_conversation_loop_streaming(
        MagicMock(),
        container,
        conversation_id="stream-tokens-test",
        content="你好",
        pinned_diaries_text="（无）",
        retrieved_diaries_text="（无）",
        episodic_text="（无）",
        memory_ids=[],
        trace_id="stream-tokens-test",
    ):
        if isinstance(item, str):
            collected.append(item)

    assert "你" in collected
    assert "好" in collected
    assert len(llm.astream_prompts) == 1  # astream called exactly once for the final reply
    clear_session("stream-tokens-test")


@pytest.mark.asyncio
async def test_run_conversation_loop_streaming_publishes_events() -> None:
    """流式 loop 应通过 TraceEventBus 发布 TEXT_DELTA 事件。"""
    clear_session("stream-events-test")
    bus = get_event_bus()
    trace_id = "stream-events-test"
    queue = await bus.subscribe(trace_id)

    llm = _StreamingStubLLM(tokens=["你", "好"])
    container = MagicMock()
    container.long_term_memory = None
    container._llm_for_tier.return_value = llm

    async for _ in run_conversation_loop_streaming(
        MagicMock(),
        container,
        conversation_id="stream-events-test",
        content="你好",
        pinned_diaries_text="（无）",
        retrieved_diaries_text="（无）",
        episodic_text="（无）",
        memory_ids=[],
        trace_id=trace_id,
    ):
        pass

    events: list[dict[str, Any]] = []
    while not queue.empty():
        events.append(queue.get_nowait())
    types = [e["type"] for e in events]

    assert StreamingEventType.REPLY_START in types
    assert StreamingEventType.TEXT_DELTA in types
    assert StreamingEventType.TEXT_END in types
    assert StreamingEventType.REPLY_END in types

    delta_events = [e for e in events if e["type"] == StreamingEventType.TEXT_DELTA]
    delta_text = "".join(e.get("text", "") for e in delta_events)
    assert "你" in delta_text
    assert "好" in delta_text

    await bus.unsubscribe(trace_id, queue)
    clear_session("stream-events-test")


@pytest.mark.asyncio
async def test_run_conversation_loop_streaming_retract_on_crisis() -> None:
    """流式过程中检测到危机应发布 RETRACT 并停止。"""
    clear_session("stream-retract-test")
    bus = get_event_bus()
    trace_id = "stream-retract-test"
    queue = await bus.subscribe(trace_id)

    # LLM streams crisis content (user input itself is safe)
    llm = _StreamingStubLLM(tokens=["我不想活了"])
    container = MagicMock()
    container.long_term_memory = None
    container._llm_for_tier.return_value = llm

    collected: list[Any] = []
    async for item in run_conversation_loop_streaming(
        MagicMock(),
        container,
        conversation_id="stream-retract-test",
        content="今天好累",  # safe user input; crisis is in LLM output
        pinned_diaries_text="（无）",
        retrieved_diaries_text="（无）",
        episodic_text="（无）",
        memory_ids=[],
        intent_result=ChatIntentResult(
            intent_category="emotional_vent",
            confidence=0.9,
            need_retrieval=False,
            need_tools=[],
            need_entity_query=False,
            tier="medium",
            max_iterations=1,
        ),
        trace_id=trace_id,
    ):
        collected.append(item)

    events: list[dict[str, Any]] = []
    while not queue.empty():
        events.append(queue.get_nowait())
    types = [e["type"] for e in events]

    assert StreamingEventType.RETRACT in types

    # RETRACT dict should also be yielded to the caller
    retract_yields = [c for c in collected if isinstance(c, dict) and c.get("retract")]
    assert len(retract_yields) >= 1

    retract_events = [e for e in events if e["type"] == StreamingEventType.RETRACT]
    assert "crisis_in_stream" in retract_events[0]["reason"]

    await bus.unsubscribe(trace_id, queue)
    clear_session("stream-retract-test")


# ── P2: PlannerAgent integration for plan_exploration intent ──


def test_plan_exploration_intent_routes_to_planner_agent(db_session) -> None:
    """plan_exploration 意图应触发 PlannerAgent，不走工具循环。"""
    clear_session("conv-plan-test")

    intent = ChatIntentResult(
        intent_category="plan_exploration",
        need_tools=["list_todos", "get_plan_progress"],
        tier="heavy",
        max_iterations=5,
    )

    fake_response = MagicMock()
    fake_response.content = "placeholder"
    fake_response.response_metadata = {
        "token_usage": {"total_tokens": 10, "prompt_tokens": 5, "completion_tokens": 5}
    }
    llm = MagicMock()
    llm.invoke.return_value = fake_response

    container = MagicMock()
    container.long_term_memory = None
    container._llm_for_tier.return_value = llm

    with patch(
        "app.domain.agents.planner_agent.PlannerAgent.run",
        new_callable=AsyncMock,
    ) as mock_planner_run:
        result = run_conversation_loop(
            db_session,
            container,
            conversation_id="conv-plan-test",
            content="帮我规划早睡",
            pinned_diaries_text="",
            retrieved_diaries_text="",
            episodic_text="",
            memory_ids=[],
            intent_result=intent,
            user_id="user-1",
            use_graph=False,  # force the legacy loop
        )
        # PlannerAgent.run must be invoked exactly once.
        assert mock_planner_run.called
        assert mock_planner_run.call_count == 1
        # The loop returns a completed result without entering the Agentic Loop.
        assert result.stop_reason == "completed"

    clear_session("conv-plan-test")


def test_non_plan_intent_does_not_route_to_planner(db_session) -> None:
    """非 plan 意图不应触发 PlannerAgent。"""
    clear_session("conv-casual")

    intent = ChatIntentResult(
        intent_category="casual_chat",
        tier="light",
        max_iterations=1,
    )

    fake_response = MagicMock()
    fake_response.content = "你好呀，今天怎么样？"
    fake_response.response_metadata = {
        "token_usage": {"total_tokens": 50, "prompt_tokens": 40, "completion_tokens": 10}
    }
    llm = MagicMock()
    llm.invoke.return_value = fake_response

    container = MagicMock()
    container.long_term_memory = None
    container._llm_for_tier.return_value = llm

    with patch(
        "app.domain.agents.planner_agent.PlannerAgent.run",
        new_callable=AsyncMock,
    ) as mock_planner_run:
        result = run_conversation_loop(
            db_session,
            container,
            conversation_id="conv-casual",
            content="你好",
            pinned_diaries_text="",
            retrieved_diaries_text="",
            episodic_text="",
            memory_ids=[],
            intent_result=intent,
            user_id="user-1",
            use_graph=False,
        )
        # PlannerAgent must NOT be called for a casual_chat intent.
        assert not mock_planner_run.called
        assert result.stop_reason == "completed"

    clear_session("conv-casual")


@pytest.mark.asyncio
async def test_plan_exploration_streaming_routes_to_planner_agent() -> None:
    """流式 loop 中 plan_exploration 应委托给 PlannerAgent 并提前返回。"""
    clear_session("conv-plan-stream")

    intent = ChatIntentResult(
        intent_category="plan_exploration",
        need_tools=["list_todos"],
        tier="heavy",
        max_iterations=5,
    )

    llm = _StreamingStubLLM(tokens=["不", "应", "到", "达"])

    container = MagicMock()
    container.long_term_memory = None
    container._llm_for_tier.return_value = llm

    with patch(
        "app.domain.agents.planner_agent.PlannerAgent.run",
        new_callable=AsyncMock,
    ) as mock_planner_run:
        collected: list[Any] = []
        async for item in run_conversation_loop_streaming(
            MagicMock(),
            container,
            conversation_id="conv-plan-stream",
            content="帮我规划早睡",
            pinned_diaries_text="",
            retrieved_diaries_text="",
            episodic_text="",
            memory_ids=[],
            intent_result=intent,
            user_id="user-1",
            trace_id="conv-plan-stream",
        ):
            collected.append(item)

        # PlannerAgent.run was awaited exactly once.
        assert mock_planner_run.called
        assert mock_planner_run.call_count == 1
        # The streaming Agentic Loop must not be entered, so no LLM tokens are
        # yielded from astream.
        assert collected == []
        assert llm.astream_prompts == []

    clear_session("conv-plan-stream")
