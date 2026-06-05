"""Unit tests for ExecutionPlanner routing."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.ai.router import ExecutionMode, ExecutionPlanner
from app.shared.llm_factory import StubLLMClient
from app.shared.tracing import InMemoryAgentDecisionLogger


def test_plan_light_for_short_diary() -> None:
    planner = ExecutionPlanner(llm_by_tier={"default": StubLLMClient()})
    decision = planner.plan(diary_id=1, content="今天还行。", diary_length=5)
    assert decision.tier == "light"
    assert decision.mode == ExecutionMode.CHAIN


def test_plan_agent_for_temporal_keywords() -> None:
    planner = ExecutionPlanner(
        llm_by_tier={"default": StubLLMClient()},
        db=MagicMock(),
        retriever=MagicMock(),
        multi_agent_enabled=False,
    )
    decision = planner.plan(
        diary_id=1,
        content="昨天加班到很晚，今天又这样了。",
        diary_length=20,
    )
    assert decision.mode == ExecutionMode.AGENT


def test_execute_chain_records_decision_trace() -> None:
    logger = InMemoryAgentDecisionLogger()
    planner = ExecutionPlanner(
        llm_by_tier={"light": StubLLMClient(), "default": StubLLMClient()},
        decision_logger=logger,
        multi_agent_enabled=False,
    )
    result = planner.execute(
        diary_id=42,
        context={
            "current_content": "今天心情平静。",
            "tags_context": "（未设置标签）",
            "history_summary": "（暂无历史记录）",
            "weather_info": "晴",
        },
        content="今天心情平静。",
    )
    assert result.ai_ans
    assert result.agent_mode == "chain"
    assert len(logger.records) == 1
    assert logger.records[0].tier in {"light", "medium", "heavy"}
