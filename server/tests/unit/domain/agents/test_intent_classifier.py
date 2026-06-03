"""Unit tests for IntentClassifier (rule layer + LLM layer, all mocked)."""

from __future__ import annotations

from app.domain.agents.intent_classifier import IntentClassifier
from app.domain.agents.types import IntentCategory
from app.shared.tracing import InMemoryLLMCallTracer

from .conftest import FakeMessage, usage_metadata


class _JsonLLM:
    """LLM stub returning a fixed classification JSON; counts invocations."""

    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.call_count = 0

    def invoke(self, prompt: str) -> FakeMessage:  # pragma: no cover - sync unused
        self.call_count += 1
        return FakeMessage(content=self.payload, response_metadata=usage_metadata())

    async def ainvoke(self, prompt: str) -> FakeMessage:
        self.call_count += 1
        return FakeMessage(content=self.payload, response_metadata=usage_metadata())


async def test_empty_content_is_pure_record_without_llm() -> None:
    llm = _JsonLLM("{}")
    classifier = IntentClassifier(llm)
    result = await classifier.classify("   ")
    assert result.intent_category == IntentCategory.PURE_RECORD.value
    assert result.confidence == 1.0
    assert llm.call_count == 0


async def test_rule_layer_high_confidence_skips_llm() -> None:
    llm = _JsonLLM("{}")
    classifier = IntentClassifier(llm)
    # Two strong temporal cues + two analysis cues -> retrospective_review, conf > 0.9.
    result = await classifier.classify("昨天上周那次复盘，我一直在反思为什么总是焦虑崩溃。")
    assert result.intent_category == IntentCategory.RETROSPECTIVE_REVIEW.value
    assert result.need_retrieval is True
    assert llm.call_count == 0


async def test_strong_emotion_routes_to_emotional_support() -> None:
    classifier = IntentClassifier()
    result = await classifier.classify("我好崩溃，特别焦虑，撑不住了。")
    assert result.intent_category == IntentCategory.EMOTIONAL_SUPPORT.value
    assert result.need_analysis is True


async def test_llm_layer_invoked_on_ambiguous_input_and_traced() -> None:
    payload = (
        '{"intent_category": "habit_tracking", "need_retrieval": false, '
        '"need_weather": false, "need_analysis": true, "confidence": 0.82}'
    )
    llm = _JsonLLM(payload)
    tracer = InMemoryLLMCallTracer()
    classifier = IntentClassifier(llm, tracer=tracer, model="deepseek-chat")

    result = await classifier.classify("最近想坚持早睡，但好像做得一般，写下来看看。")

    assert llm.call_count == 1
    assert result.intent_category == IntentCategory.HABIT_TRACKING.value
    assert result.confidence == 0.82
    assert len(tracer.records) == 1
    record = tracer.records[0]
    assert record.agent_name == "intent_classifier"
    assert record.call_type == "classify"
    assert record.tier == "light"
    assert record.error is None


async def test_llm_failure_falls_back_to_rule_result_and_records_error() -> None:
    class _BoomLLM:
        async def ainvoke(self, prompt: str) -> str:
            raise RuntimeError("boom")

        def invoke(self, prompt: str) -> str:  # pragma: no cover
            raise RuntimeError("boom")

    tracer = InMemoryLLMCallTracer()
    classifier = IntentClassifier(_BoomLLM(), tracer=tracer)
    result = await classifier.classify("随便写点东西看看吧，没什么特别的。")

    # Falls back to a valid rule-layer result rather than raising.
    assert result.intent_category in {c.value for c in IntentCategory}
    assert len(tracer.records) == 1
    assert tracer.records[0].error is not None


async def test_llm_unparseable_output_degrades_to_rule_hint() -> None:
    llm = _JsonLLM("not a json at all")
    classifier = IntentClassifier(llm)
    result = await classifier.classify("今天天气一般，随手记录一下心情。")
    # Parsing fails -> rule hint with bumped confidence, no exception.
    assert result.intent_category in {c.value for c in IntentCategory}
    assert result.confidence >= 0.6


async def test_no_llm_returns_rule_result() -> None:
    classifier = IntentClassifier()
    result = await classifier.classify("今天去了公园，记录一下。")
    assert result.intent_category == IntentCategory.PURE_RECORD.value
