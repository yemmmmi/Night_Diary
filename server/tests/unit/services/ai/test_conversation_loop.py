"""Tests for ConversationLoop — the Agentic Loop engine."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.domain.agents.types import ChatIntentResult
from app.services.ai.conversation_loop import (
    _needs_tool_call,
    run_conversation_loop,
)
from app.services.ai.session_context import clear_session
from app.shared.llm_factory import StubLLMClient
from app.shared.tool_protocol import ToolCallResult, parse_text_tag_calls


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
        return_value=StubLLMClient(
            reply="<tool>search_diary</tool><args>{\"query\": \"工作\"}</args>"
        )
    )
    container.ensure_ai_stack = MagicMock()

    with patch(
        "app.services.ai.conversation_loop.parse_text_tag_calls"
    ) as mock_parse:
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
    )

    # No citations, no "参考来源" section
    assert len(result.citations) == 0
    assert "参考来源" not in result.reply_text
    clear_session("no-citation-test")
