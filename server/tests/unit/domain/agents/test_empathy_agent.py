"""Unit tests for EmpathyAgent (LLM mocked, crisis + fallback paths)."""

from __future__ import annotations

from app.domain.agents.empathy_agent import EmpathyAgent
from app.domain.skills.crisis_detector import CRISIS_RESOURCES
from app.shared.tracing import InMemoryLLMCallTracer

from .conftest import FailingLLM, FakeLLM, StubKnowledgeStore


async def test_normal_reply_returns_response_and_token_usage(
    fake_llm: FakeLLM,
    knowledge_store: StubKnowledgeStore,
    llm_tracer: InMemoryLLMCallTracer,
) -> None:
    agent = EmpathyAgent(fake_llm, knowledge_store, tracer=llm_tracer, model="deepseek-chat")
    result = await agent.run(
        {"diary_content": "今天工作很顺利，心情不错。", "intent": "pure_record"}
    )
    assert result["empathy_response"] == fake_llm.reply
    assert result["total_tokens_used"] == 180
    assert result["output_tokens"] == 60
    assert CRISIS_RESOURCES not in result["empathy_response"]


async def test_llm_call_is_traced(
    fake_llm: FakeLLM,
    knowledge_store: StubKnowledgeStore,
    llm_tracer: InMemoryLLMCallTracer,
) -> None:
    agent = EmpathyAgent(fake_llm, knowledge_store, tracer=llm_tracer, model="deepseek-chat")
    await agent.run({"diary_content": "今天还行。", "intent": "pure_record"})

    assert len(llm_tracer.records) == 1
    record = llm_tracer.records[0]
    assert record.agent_name == "empathy"
    assert record.call_type == "generate"
    assert record.tier == "medium"
    assert record.tokens_out == 60
    assert record.error is None


async def test_crisis_text_appends_resources_and_marks_crisis_tier(
    fake_llm: FakeLLM,
    knowledge_store: StubKnowledgeStore,
    llm_tracer: InMemoryLLMCallTracer,
) -> None:
    agent = EmpathyAgent(fake_llm, knowledge_store, tracer=llm_tracer)
    result = await agent.run(
        {"diary_content": "我不想活了，撑不下去，觉得绝望又崩溃。", "intent": "emotional_support"}
    )
    assert CRISIS_RESOURCES in result["empathy_response"]
    assert llm_tracer.records[0].tier == "crisis"


async def test_fallback_when_llm_unreachable(
    failing_llm: FailingLLM,
    knowledge_store: StubKnowledgeStore,
    llm_tracer: InMemoryLLMCallTracer,
) -> None:
    agent = EmpathyAgent(failing_llm, knowledge_store, tracer=llm_tracer)
    result = await agent.run(
        {"diary_content": "今天压力有点大。", "intent": "emotional_support"}
    )
    # No exception; safe template returned; the failed call is still traced.
    assert "empathy_response" in result
    assert result["empathy_response"]
    assert "total_tokens_used" not in result
    assert llm_tracer.records[0].error is not None


async def test_crisis_fallback_includes_resources(
    failing_llm: FailingLLM,
    knowledge_store: StubKnowledgeStore,
) -> None:
    agent = EmpathyAgent(failing_llm, knowledge_store)
    result = await agent.run(
        {"diary_content": "我不想活了，自残割腕，没有希望了。", "intent": "emotional_support"}
    )
    assert CRISIS_RESOURCES in result["empathy_response"]


async def test_style_fragment_is_injected_into_prompt(
    fake_llm: FakeLLM,
    knowledge_store: StubKnowledgeStore,
) -> None:
    agent = EmpathyAgent(fake_llm, knowledge_store)
    await agent.run(
        {"diary_content": "今天有点累。", "intent": "emotional_support"},
        style_fragment="## 用户偏好：请用务实风格回应",
    )
    assert "用户偏好：请用务实风格回应" in fake_llm.calls[0]


def test_fallback_direct_call_uses_intent_template(
    fake_llm: FakeLLM,
    knowledge_store: StubKnowledgeStore,
) -> None:
    agent = EmpathyAgent(fake_llm, knowledge_store)
    result = agent.fallback("habit_tracking")
    assert "习惯" in result["empathy_response"]
