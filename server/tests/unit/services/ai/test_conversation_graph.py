"""Tests for conversation_graph — LangGraph StateGraph orchestration."""

from __future__ import annotations

import pytest

from app.services.ai.conversation_graph import (
    LANGGRAPH_AVAILABLE,
    build_conversation_graph,
    run_conversation_graph,
)

# ── Graph availability tests ────────────────────────────────────────


@pytest.mark.skipif(
    not LANGGRAPH_AVAILABLE,
    reason="LangGraph not installed",
)
def test_build_conversation_graph_returns_compiled_graph() -> None:
    """build_conversation_graph returns a compiled graph when LangGraph is available."""
    graph = build_conversation_graph()
    assert graph is not None
    # Compiled graph should have an 'invoke' method
    assert hasattr(graph, "invoke")


def test_build_conversation_graph_returns_none_without_langgraph() -> None:
    """If LangGraph is not installed, build_conversation_graph returns None."""
    if not LANGGRAPH_AVAILABLE:
        graph = build_conversation_graph()
        assert graph is None


# ── Graph execution tests (only when LangGraph is available) ────────


@pytest.mark.skipif(
    not LANGGRAPH_AVAILABLE,
    reason="LangGraph not installed",
)
def test_run_conversation_graph_simple_reply() -> None:
    """Graph produces a reply for simple input (no tools)."""
    from app.shared.llm_factory import StubLLMClient

    graph = build_conversation_graph()
    llm = StubLLMClient(reply="你好，今天怎么样？")

    final_state = run_conversation_graph(
        graph,
        content="你好",
        llm=llm,
        system_prompt="你是夜记AI助手。",
        conversation_id="test-simple",
    )

    assert "final_response" in final_state
    assert len(final_state["final_response"]) > 0
    assert final_state["stop_reason"] == "completed"


@pytest.mark.skipif(
    not LANGGRAPH_AVAILABLE,
    reason="LangGraph not installed",
)
def test_run_conversation_graph_no_llm_returns_fallback() -> None:
    """Graph returns fallback when no LLM is provided."""
    graph = build_conversation_graph()

    final_state = run_conversation_graph(
        graph,
        content="你好",
        llm=None,
        conversation_id="test-no-llm",
    )

    assert "final_response" in final_state
    assert final_state["stop_reason"] == "no_llm"


@pytest.mark.skipif(
    not LANGGRAPH_AVAILABLE,
    reason="LangGraph not installed",
)
def test_run_conversation_graph_with_citations() -> None:
    """Graph tracks citations for context sources."""
    from app.shared.llm_factory import StubLLMClient

    graph = build_conversation_graph()
    llm = StubLLMClient(reply="根据你的日记...")

    final_state = run_conversation_graph(
        graph,
        content="查一下最近的日记",
        llm=llm,
        system_prompt="你是夜记AI助手。",
        pinned_diaries_text="昨天很开心",
        retrieved_diaries_text="上周去了公园",
        episodic_text="之前聊过工作压力",
        conversation_id="test-citations",
    )

    assert "citations" in final_state
    assert len(final_state["citations"]) >= 3  # pinned + retrieved + episodic
    source_types = [c.source_type for c in final_state["citations"]]
    assert "diary" in source_types
    assert "memory" in source_types
    assert "参考来源" in final_state["final_response"]


@pytest.mark.skipif(
    not LANGGRAPH_AVAILABLE,
    reason="LangGraph not installed",
)
def test_run_conversation_graph_error_handling() -> None:
    """Graph error handling returns fallback response."""
    graph = build_conversation_graph()

    # Pass an LLM that raises on invoke
    class FailingLLM:
        def invoke(self, prompt):
            raise RuntimeError("LLM unavailable")

        def ainvoke(self, prompt):
            raise RuntimeError("LLM unavailable")

    final_state = run_conversation_graph(
        graph,
        content="你好",
        llm=FailingLLM(),
        conversation_id="test-error",
    )

    assert "final_response" in final_state
    # Should have fallback response, not crash
    assert len(final_state["final_response"]) > 0


# ── Container integration tests ─────────────────────────────────────


def test_container_get_conversation_graph_caches() -> None:
    """Container caches the conversation graph."""
    from app.services.container import ServiceContainer

    container = ServiceContainer.create_core()
    graph1 = container.get_conversation_graph()
    graph2 = container.get_conversation_graph()
    # Same instance (cached)
    assert graph1 is graph2
