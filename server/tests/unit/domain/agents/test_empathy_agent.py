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


async def test_user_preset_overrides_profile_style(
    fake_llm: FakeLLM,
    knowledge_store: StubKnowledgeStore,
) -> None:
    """传 style_fragment 时, fragment 应替代 (而非追加) profile 推导出的风格指令。

    构造一个 preferred_response_style="practical" 的 profile (旧 key, 会归一化成
    pragmatic), 同时传一段带独特标记的 fragment, 验证:
      1. fragment 内容进入 prompt;
      2. 不再出现 ``## 回应风格`` 标题与旧 ``务实关怀`` 文案 —— 证明 fragment 覆盖了
         profile 风格, 两段风格指令没有同时存在打架。
    """
    agent = EmpathyAgent(fake_llm, knowledge_store)
    fragment = "## 回信风格（用户指定，优先级最高）\n【测试标记】请用诗意的短句回信。"
    await agent.run(
        {
            "diary_content": "今天有点累。",
            "intent": "emotional_support",
            "long_term_profile": {"preferred_response_style": "practical"},
        },
        style_fragment=fragment,
    )
    prompt = fake_llm.calls[0]
    # fragment 内容进入 prompt
    assert "【测试标记】请用诗意的短句回信。" in prompt
    # fragment 覆盖了 profile 推导出的风格指令: 不应再出现 ## 回应风格 标题
    assert "## 回应风格" not in prompt
    # 旧文案字样也不应出现 (回归保护)
    assert "## 回应风格\n务实关怀" not in prompt


def test_fallback_direct_call_uses_intent_template(
    fake_llm: FakeLLM,
    knowledge_store: StubKnowledgeStore,
) -> None:
    agent = EmpathyAgent(fake_llm, knowledge_store)
    result = agent.fallback("habit_tracking")
    assert "习惯" in result["empathy_response"]
