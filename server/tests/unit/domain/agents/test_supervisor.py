"""Unit tests for SupervisorAgent: intent routing, Skill integration, synthesis.

The IntentClassifier is stubbed (async, returns a fixed IntentResult) so routing
is deterministic; the SkillRegistry is the *real* default registry wired with an
in-memory activation tracer so the B-6 → B-9 Skill integration (and the
decision_id linkage) is exercised end to end. LLM access uses the shared
FakeLLM/FailingLLM doubles from conftest.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.domain.agents.supervisor import (
    CRISIS_TOKEN_BUDGET,
    DEFAULT_TOKEN_BUDGET,
    SupervisorAgent,
    allocate_token_budget,
)
from app.domain.agents.types import IntentCategory, IntentResult
from app.domain.skills.registry import create_default_registry
from app.shared.tracing import (
    InMemoryAgentDecisionLogger,
    InMemoryLLMCallTracer,
    InMemorySkillActivationTracer,
)


class StubIntentClassifier:
    """Async classifier returning a preset IntentResult."""

    def __init__(self, result: IntentResult) -> None:
        self._result = result
        self.calls: list[str] = []

    async def classify(self, content: str) -> IntentResult:
        self.calls.append(content)
        return self._result


class BoomClassifier:
    """Classifier that always raises — drives the supervisor's safe default."""

    async def classify(self, content: str) -> IntentResult:
        raise RuntimeError("classifier unreachable")


def _make_supervisor(
    intent: str = IntentCategory.PURE_RECORD.value,
    *,
    confidence: float = 0.9,
    llm: Any = None,
    classifier: Any | None = None,
) -> tuple[SupervisorAgent, InMemoryAgentDecisionLogger, InMemorySkillActivationTracer]:
    decision_logger = InMemoryAgentDecisionLogger()
    skill_tracer = InMemorySkillActivationTracer()
    classifier = classifier or StubIntentClassifier(
        IntentResult(intent_category=intent, confidence=confidence)
    )
    supervisor = SupervisorAgent(
        classifier,
        create_default_registry(skill_tracer),
        llm=llm,
        decision_logger=decision_logger,
        llm_tracer=InMemoryLLMCallTracer(),
    )
    return supervisor, decision_logger, skill_tracer


# ----- allocate_token_budget -----


def test_allocate_token_budget_midpoint_and_crisis() -> None:
    assert allocate_token_budget(IntentCategory.PURE_RECORD.value) == 500
    assert allocate_token_budget(IntentCategory.EMOTIONAL_SUPPORT.value) == 1250
    assert allocate_token_budget("unknown_intent") == DEFAULT_TOKEN_BUDGET
    assert allocate_token_budget(IntentCategory.PURE_RECORD.value, is_crisis=True) == (
        CRISIS_TOKEN_BUDGET
    )


# ----- classify / routing -----


@pytest.mark.parametrize(
    ("intent", "expected"),
    [
        (IntentCategory.PURE_RECORD.value, ["empathy"]),
        (IntentCategory.EMOTIONAL_SUPPORT.value, ["empathy", "retrieval"]),
        (
            IntentCategory.RETROSPECTIVE_REVIEW.value,
            ["empathy", "retrieval", "insight"],
        ),
        (IntentCategory.HABIT_TRACKING.value, ["retrieval", "insight"]),
    ],
)
async def test_classify_routes_by_intent(intent: str, expected: list[str]) -> None:
    supervisor, _, _ = _make_supervisor(intent)
    update = await supervisor.classify({"diary_content": "今天去公园散步，天气很好。"})

    assert update["intent"] == intent
    assert sorted(update["activated_agents"]) == sorted(expected)
    assert update["tier"] != "crisis"


async def test_low_confidence_routes_to_empathy_only() -> None:
    supervisor, _, _ = _make_supervisor(
        IntentCategory.RETROSPECTIVE_REVIEW.value, confidence=0.3
    )
    update = await supervisor.classify({"diary_content": "今天做了很多事情。"})
    assert update["activated_agents"] == ["empathy"]


async def test_crisis_short_circuits_to_empathy() -> None:
    supervisor, _, _ = _make_supervisor(IntentCategory.EMOTIONAL_SUPPORT.value)
    update = await supervisor.classify(
        {"diary_content": "我真的撑不下去了，不想活了，想结束这一切。"}
    )
    assert update["tier"] == "crisis"
    assert update["activated_agents"] == ["empathy"]
    assert update["token_budget"] == CRISIS_TOKEN_BUDGET


async def test_classifier_failure_defaults_to_pure_record() -> None:
    supervisor, _, _ = _make_supervisor(classifier=BoomClassifier())
    update = await supervisor.classify({"diary_content": "随便记录一下。"})
    assert update["intent"] == IntentCategory.PURE_RECORD.value
    assert update["activated_agents"] == ["empathy"]


# ----- Skill integration (the B-9 hard gate) -----


async def test_skills_selected_and_linked_to_decision() -> None:
    supervisor, decisions, skill_tracer = _make_supervisor(
        IntentCategory.EMOTIONAL_SUPPORT.value
    )
    update = await supervisor.classify(
        {"diary_id": "d1", "diary_content": "今天特别难过，心里很堵，想找人说说话。"}
    )

    # select_skills ran and produced activations.
    assert len(update["activated_skills"]) > 0
    assert len(skill_tracer.records) > 0

    # The skill_activation decision carries the activated skill ids ...
    skill_decisions = [d for d in decisions.records if d.decision_type == "skill_activation"]
    assert len(skill_decisions) == 1
    decision = skill_decisions[0]
    assert set(decision.skill_ids) == set(update["activated_skills"])

    # ... and every activation row links back to that decision via decision_id.
    assert all(record.decision_id == decision.id for record in skill_tracer.records)


async def test_classify_logs_all_decision_types() -> None:
    supervisor, decisions, _ = _make_supervisor(IntentCategory.RETROSPECTIVE_REVIEW.value)
    await supervisor.classify({"diary_id": "d2", "diary_content": "回顾了这一周的经历。"})

    logged = {d.decision_type for d in decisions.records}
    assert logged == {
        "intent_classification",
        "skill_activation",
        "tier_routing",
        "worker_routing",
    }


# ----- synthesize -----


async def test_synthesize_crisis_returns_empathy_verbatim() -> None:
    supervisor, _, _ = _make_supervisor()
    state = {"tier": "crisis", "empathy_response": "我在这里陪着你，请拨打热线 400-161-9995。"}
    update = await supervisor.synthesize(state)
    assert update["final_response"] == state["empathy_response"]


async def test_synthesize_uses_llm_when_multiple_outputs(fake_llm: Any) -> None:
    supervisor, _, _ = _make_supervisor(llm=fake_llm)
    state = {
        "intent": IntentCategory.RETROSPECTIVE_REVIEW.value,
        "token_budget": 1500,
        "empathy_response": "我理解你的感受。",
        "insight_response": "你最近的拖延可能与压力有关。",
    }
    update = await supervisor.synthesize(state)
    assert update["final_response"] == fake_llm.reply
    assert fake_llm.calls  # the synthesis LLM was actually invoked
    assert update["total_tokens_used"] > 0


async def test_synthesize_simple_join_without_llm() -> None:
    supervisor, _, _ = _make_supervisor(llm=None)
    state = {
        "empathy_response": "共情部分。",
        "insight_response": "洞察部分。",
    }
    update = await supervisor.synthesize(state)
    assert "共情部分。" in update["final_response"]
    assert "洞察部分。" in update["final_response"]


async def test_synthesize_single_output_skips_llm(fake_llm: Any) -> None:
    supervisor, _, _ = _make_supervisor(llm=fake_llm)
    state = {"empathy_response": "只有共情。"}
    update = await supervisor.synthesize(state)
    assert update["final_response"] == "只有共情。"
    assert not fake_llm.calls


async def test_synthesize_fallback_when_all_empty() -> None:
    supervisor, _, _ = _make_supervisor()
    update = await supervisor.synthesize({"errors": ["worker 'empathy' failed"]})
    assert update["final_response"]  # non-empty safe fallback
    assert update["agent_mode"] == "multi_agent"
