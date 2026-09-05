"""Unit tests for InsightAgent (LLM mocked, report + deviation + fallback)."""

from __future__ import annotations

from app.domain.agents.insight_agent import InsightAgent
from app.domain.agents.prompts import INSIGHT_FALLBACK
from app.shared.tracing import InMemoryLLMCallTracer

from .conftest import FailingLLM, FakeLLM, StubKnowledgeStore


async def test_normal_analysis_returns_response_and_usage(
    fake_llm: FakeLLM,
    knowledge_store: StubKnowledgeStore,
    llm_tracer: InMemoryLLMCallTracer,
) -> None:
    agent = InsightAgent(fake_llm, knowledge_store, tracer=llm_tracer, model="deepseek-chat")
    result = await agent.run(
        {"diary_content": "为什么我总是焦虑？想找找规律。", "intent": "emotional_support"}
    )
    assert result["insight_response"] == fake_llm.reply
    assert result["total_tokens_used"] == 180


async def test_llm_call_is_traced_as_heavy(
    fake_llm: FakeLLM,
    knowledge_store: StubKnowledgeStore,
    llm_tracer: InMemoryLLMCallTracer,
) -> None:
    agent = InsightAgent(fake_llm, knowledge_store, tracer=llm_tracer)
    await agent.run({"diary_content": "想复盘一下最近的状态。"})
    assert len(llm_tracer.records) == 1
    record = llm_tracer.records[0]
    assert record.agent_name == "insight"
    assert record.tier == "heavy"
    assert record.tokens_out == 60


async def test_weekly_report_uses_report_prompt(
    fake_llm: FakeLLM,
    knowledge_store: StubKnowledgeStore,
) -> None:
    agent = InsightAgent(fake_llm, knowledge_store)
    await agent.run({"diary_content": "帮我生成这周的周报，回顾一下本周。"})
    assert "周报" in fake_llm.calls[0]
    assert "趋势方向" in fake_llm.calls[0]


async def test_emotion_deviation_added_when_recent_diverges_from_baseline(
    fake_llm: FakeLLM,
    knowledge_store: StubKnowledgeStore,
) -> None:
    agent = InsightAgent(fake_llm, knowledge_store)
    await agent.run(
        {
            "diary_content": "最近怎么了。",
            "long_term_profile": {"emotion_baseline": {"average_sentiment": 0.5}},
            "episodic_context": [
                {"event": "和朋友吵架", "emotion": "愤怒", "importance": 0.9},
                {"event": "工作出错", "emotion": "焦虑", "importance": 0.8},
            ],
        }
    )
    assert "情绪偏离提醒" in fake_llm.calls[0]


async def test_no_deviation_without_episodic_context(
    fake_llm: FakeLLM,
    knowledge_store: StubKnowledgeStore,
) -> None:
    agent = InsightAgent(fake_llm, knowledge_store)
    await agent.run({"diary_content": "今天挺平静的。"})
    assert "情绪偏离提醒" not in fake_llm.calls[0]


async def test_fallback_when_llm_unreachable(
    failing_llm: FailingLLM,
    knowledge_store: StubKnowledgeStore,
    llm_tracer: InMemoryLLMCallTracer,
) -> None:
    agent = InsightAgent(failing_llm, knowledge_store, tracer=llm_tracer)
    result = await agent.run({"diary_content": "想分析一下最近的情绪。"})
    assert result["insight_response"] == INSIGHT_FALLBACK
    assert "total_tokens_used" not in result
    assert llm_tracer.records[0].error is not None


async def test_style_fragment_injected(
    fake_llm: FakeLLM,
    knowledge_store: StubKnowledgeStore,
) -> None:
    agent = InsightAgent(fake_llm, knowledge_store)
    await agent.run(
        {"diary_content": "复盘一下。"},
        style_fragment="## 偏好：数据驱动、结论明确",
    )
    assert "数据驱动、结论明确" in fake_llm.calls[0]


def test_fallback_direct_call(
    fake_llm: FakeLLM,
    knowledge_store: StubKnowledgeStore,
) -> None:
    agent = InsightAgent(fake_llm, knowledge_store)
    assert agent.fallback()["insight_response"] == INSIGHT_FALLBACK
