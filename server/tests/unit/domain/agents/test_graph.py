"""Unit tests for the pure-asyncio MultiAgentGraph orchestration.

Workers are lightweight fakes (async ``run`` + sync ``fallback``) so we can drive
phased execution, per-worker timeouts, exceptions, partial-failure degradation,
and reducer-based state merging without real LLMs or retrievers. The Supervisor
is real (stubbed classifier + default Skill registry) so routing decisions flow
through the actual code path.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.domain.agents.graph import create_multi_agent_graph
from app.domain.agents.supervisor import SupervisorAgent
from app.domain.agents.types import IntentCategory, IntentResult
from app.domain.skills.registry import create_default_registry
from app.shared.tracing import (
    InMemoryAgentDecisionLogger,
    InMemoryLLMCallTracer,
    InMemorySkillActivationTracer,
)


class StubIntentClassifier:
    def __init__(self, result: IntentResult) -> None:
        self._result = result

    async def classify(self, content: str) -> IntentResult:
        return self._result


class FakeWorker:
    """Configurable worker double: fixed output, optional delay/failure/tokens."""

    def __init__(
        self,
        output_key: str,
        response: str = "ok",
        *,
        delay: float = 0.0,
        fail: bool = False,
        tokens: int = 0,
        observe_key: str | None = None,
        stream_tokens: list[str] | None = None,
    ) -> None:
        self.output_key = output_key
        self.response = response
        self.delay = delay
        self.fail = fail
        self.tokens = tokens
        self.observe_key = observe_key
        self.observed: Any = None
        self.ran = False
        self.fallback_called = False
        self.style_fragment_seen: str | None = None
        # When set, run_streaming yields these token-by-token; otherwise it
        # degrades to emitting ``response`` as a single chunk (matching the
        # supervisor's "worker lacks streaming support" fallback path).
        self.stream_tokens = stream_tokens

    async def run(
        self,
        state: dict[str, Any],
        *,
        style_fragment: str | None = None,
    ) -> dict[str, Any]:
        self.ran = True
        self.style_fragment_seen = style_fragment
        if self.observe_key is not None:
            self.observed = state.get(self.observe_key)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError("worker boom")
        update: dict[str, Any] = {self.output_key: self.response}
        if self.tokens:
            update["total_tokens_used"] = self.tokens
        return update

    async def run_streaming(self, state: dict[str, Any]) -> Any:
        """Token stream used by ``supervisor.synthesize_streaming``."""
        if self.stream_tokens is not None:
            for token in self.stream_tokens:
                yield token
        else:
            yield self.response

    def fallback(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.fallback_called = True
        return {self.output_key: f"[fallback:{self.output_key}]"}


def _make_graph(
    intent: str,
    *,
    empathy: FakeWorker,
    retrieval: FakeWorker,
    insight: FakeWorker,
    confidence: float = 0.9,
    worker_timeout_s: float = 30.0,
) -> Any:
    supervisor = SupervisorAgent(
        StubIntentClassifier(
            IntentResult(intent_category=intent, confidence=confidence, need_retrieval=True)
        ),
        create_default_registry(InMemorySkillActivationTracer()),
        llm=None,
        decision_logger=InMemoryAgentDecisionLogger(),
        llm_tracer=InMemoryLLMCallTracer(),
    )
    return create_multi_agent_graph(
        supervisor, empathy, retrieval, insight, worker_timeout_s=worker_timeout_s
    )


def _state(content: str = "今天平平淡淡地过了一天，记录一下。") -> dict[str, Any]:
    return {"diary_id": "d1", "diary_content": content}


async def test_full_pipeline_runs_activated_workers() -> None:
    empathy = FakeWorker("empathy_response", "共情回应")
    retrieval = FakeWorker("retrieval_context", "历史片段")
    insight = FakeWorker("insight_response", "洞察结论")
    graph = _make_graph(
        IntentCategory.RETROSPECTIVE_REVIEW.value,
        empathy=empathy,
        retrieval=retrieval,
        insight=insight,
    )

    result = await graph.invoke(_state())

    assert empathy.ran and retrieval.ran and insight.ran
    assert "共情回应" in result["final_response"]
    assert "洞察结论" in result["final_response"]
    assert result.get("errors", []) == []


async def test_retrieval_runs_before_consumers() -> None:
    empathy = FakeWorker("empathy_response", "共情", observe_key="retrieval_context")
    retrieval = FakeWorker("retrieval_context", "HISTORY")
    insight = FakeWorker("insight_response", "洞察", observe_key="retrieval_context")
    graph = _make_graph(
        IntentCategory.RETROSPECTIVE_REVIEW.value,
        empathy=empathy,
        retrieval=retrieval,
        insight=insight,
    )

    await graph.invoke(_state())

    # Consumers observed the provider's output (phased execution, not a free-for-all).
    assert insight.observed == "HISTORY"
    assert empathy.observed == "HISTORY"


async def test_worker_timeout_falls_back() -> None:
    empathy = FakeWorker("empathy_response", "慢回应", delay=1.0)
    retrieval = FakeWorker("retrieval_context", "x")
    insight = FakeWorker("insight_response", "x")
    graph = _make_graph(
        IntentCategory.PURE_RECORD.value,
        empathy=empathy,
        retrieval=retrieval,
        insight=insight,
        worker_timeout_s=0.05,
    )

    result = await graph.invoke(_state())

    assert empathy.fallback_called
    assert "[fallback:empathy_response]" in result["final_response"]
    assert any("timeout" in e for e in result["errors"])


async def test_worker_exception_falls_back() -> None:
    empathy = FakeWorker("empathy_response", fail=True)
    retrieval = FakeWorker("retrieval_context", "x")
    insight = FakeWorker("insight_response", "x")
    graph = _make_graph(
        IntentCategory.PURE_RECORD.value,
        empathy=empathy,
        retrieval=retrieval,
        insight=insight,
    )

    result = await graph.invoke(_state())

    assert empathy.fallback_called
    assert any("failed" in e for e in result["errors"])


async def test_partial_failure_is_degraded_not_fatal() -> None:
    empathy = FakeWorker("empathy_response", "我在这里陪你")
    retrieval = FakeWorker("retrieval_context", "历史")
    insight = FakeWorker("insight_response", fail=True)
    graph = _make_graph(
        IntentCategory.RETROSPECTIVE_REVIEW.value,
        empathy=empathy,
        retrieval=retrieval,
        insight=insight,
    )

    result = await graph.invoke(_state())

    # The healthy worker's output still surfaces; the failure is recorded.
    assert "我在这里陪你" in result["final_response"]
    assert len(result["errors"]) == 1
    assert insight.fallback_called


async def test_token_counts_are_summed_via_reducer() -> None:
    empathy = FakeWorker("empathy_response", "a", tokens=100)
    retrieval = FakeWorker("retrieval_context", "b", tokens=40)
    insight = FakeWorker("insight_response", "c")
    graph = _make_graph(
        IntentCategory.EMOTIONAL_SUPPORT.value,  # empathy + retrieval
        empathy=empathy,
        retrieval=retrieval,
        insight=insight,
    )

    result = await graph.invoke(_state())
    assert result["total_tokens_used"] == 140


async def test_crisis_routes_only_empathy_and_returns_verbatim() -> None:
    empathy = FakeWorker("empathy_response", "我在,请拨打 400-161-9995")
    retrieval = FakeWorker("retrieval_context", "应当跳过")
    insight = FakeWorker("insight_response", "应当跳过")
    graph = _make_graph(
        IntentCategory.EMOTIONAL_SUPPORT.value,
        empathy=empathy,
        retrieval=retrieval,
        insight=insight,
    )

    result = await graph.invoke(_state("我不想活了，撑不下去了。"))

    assert result["tier"] == "crisis"
    assert empathy.ran
    assert not retrieval.ran and not insight.ran
    assert result["final_response"] == "我在,请拨打 400-161-9995"


async def test_graph_compresses_episodic_before_workers() -> None:
    empathy = FakeWorker("empathy_response", "ok", observe_key="compressed_history")
    retrieval = FakeWorker("retrieval_context", "历史")
    insight = FakeWorker("insight_response", "x")
    graph = _make_graph(
        IntentCategory.EMOTIONAL_SUPPORT.value,
        empathy=empathy,
        retrieval=retrieval,
        insight=insight,
    )

    state = {
        "diary_id": "d1",
        "diary_content": "今天又失眠了。",
        "episodic_context": [
            {"event_summary": "连续三天失眠", "content": "连续三天失眠到凌晨两点，白天无法集中"},
            {"event_summary": "周末爬山", "content": "周末爬山心情不错，拍了好多照片"},
        ],
    }
    result = await graph.invoke(state)

    assert result.get("compressed_history")
    assert "失眠" in result["compressed_history"]
    assert empathy.observed and "失眠" in str(empathy.observed)


async def test_invoke_streaming_single_worker_yields_tokens() -> None:
    """invoke_streaming reuses classify+dispatch, then streams the single worker.

    PURE_RECORD routes to empathy only, so synthesize_streaming takes the
    single-worker fast path and streams empathy.run_streaming token-by-token.
    The returned final_state carries the dispatched worker output, and the
    token stream mirrors what the worker yields (not a single merged chunk).
    """
    empathy = FakeWorker("empathy_response", "你好", stream_tokens=["你", "好"])
    retrieval = FakeWorker("retrieval_context", "应当跳过")
    insight = FakeWorker("insight_response", "应当跳过")
    graph = _make_graph(
        IntentCategory.PURE_RECORD.value,
        empathy=empathy,
        retrieval=retrieval,
        insight=insight,
    )

    final_state, token_stream = await graph.invoke_streaming(
        _state(), workers={"empathy": empathy}
    )

    tokens = [token async for token in token_stream]

    # Tokens are streamed individually from empathy.run_streaming.
    assert tokens == ["你", "好"]
    # PURE_RECORD activates empathy only.
    assert empathy.ran
    assert not retrieval.ran
    assert not insight.ran
    # The dispatched worker output is present on the returned state.
    assert final_state["empathy_response"] == "你好"
    assert final_state.get("errors", []) == []


async def test_invoke_streaming_without_workers_degrades_to_single_chunk() -> None:
    """Without streaming-capable workers, synthesize_streaming emits one chunk.

    The caller may pass workers=None (or omit a worker); the supervisor then
    yields the already-computed single-worker output verbatim in one chunk
    rather than token-by-token. invoke_streaming still returns the dispatched
    state, so the caller always has the full reply even if streaming degrades.
    """
    empathy = FakeWorker("empathy_response", "完整的非流式回信")
    retrieval = FakeWorker("retrieval_context", "x")
    insight = FakeWorker("insight_response", "x")
    graph = _make_graph(
        IntentCategory.PURE_RECORD.value,
        empathy=empathy,
        retrieval=retrieval,
        insight=insight,
    )

    final_state, token_stream = await graph.invoke_streaming(_state())

    tokens = [token async for token in token_stream]

    assert tokens == ["完整的非流式回信"]
    assert final_state["empathy_response"] == "完整的非流式回信"


async def test_invoke_streaming_preserves_invoke_classification() -> None:
    """invoke_streaming produces the same classify+dispatch state shape as invoke.

    Both entry points share _classify_and_dispatch, so after dispatch the
    streaming state carries the same intent/tier/activated_agents as a plain
    invoke run would (pre-synthesize). This guards the pure-refactor guarantee.
    """
    empathy = FakeWorker("empathy_response", "回应")
    retrieval = FakeWorker("retrieval_context", "历史")
    insight = FakeWorker("insight_response", "洞察")
    intent = IntentCategory.EMOTIONAL_SUPPORT.value
    graph = _make_graph(
        intent,
        empathy=empathy,
        retrieval=retrieval,
        insight=insight,
    )

    streaming_state, _ = await graph.invoke_streaming(
        _state(), workers={"empathy": empathy}
    )

    assert streaming_state["intent"] == intent
    assert streaming_state["tier"] == "medium"
    # EMOTIONAL_SUPPORT routes empathy + retrieval; both ran during dispatch.
    assert empathy.ran and retrieval.ran
    assert "empathy" in streaming_state["activated_agents"]
    assert "retrieval" in streaming_state["activated_agents"]
