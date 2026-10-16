"""Unit tests for SkillRegistry."""

from __future__ import annotations

from app.domain.skills.base import ACTIVATION_THRESHOLD, BaseSkill
from app.domain.skills.registry import (
    SkillRegistry,
    create_chat_registry,
    create_default_registry,
    create_diary_registry,
)
from app.domain.skills.types import SkillCategory, SkillMetadata


class _HighPrioritySkill(BaseSkill):
    metadata = SkillMetadata(
        name="high_priority",
        description="test",
        triggers=["test"],
        priority=2.0,
        category=SkillCategory.ANALYSIS,
        token_cost_estimate=200,
    )

    def activation_score(self, text: str, profile=None) -> float:
        _ = (text, profile)
        return 0.9

    def execute(self, context, **kwargs) -> str:
        return "ok"


class _LowPrioritySkill(BaseSkill):
    metadata = SkillMetadata(
        name="low_priority",
        description="test",
        triggers=["test"],
        priority=0.5,
        category=SkillCategory.RETRIEVAL,
        token_cost_estimate=100,
    )

    def activation_score(self, text: str, profile=None) -> float:
        _ = (text, profile)
        return 0.8

    def execute(self, context, **kwargs) -> str:
        return "ok"


class _ExpensiveSkill(BaseSkill):
    metadata = SkillMetadata(
        name="expensive",
        description="test",
        triggers=["test"],
        priority=1.5,
        category=SkillCategory.GENERATION,
        token_cost_estimate=500,
    )

    def activation_score(self, text: str, profile=None) -> float:
        _ = (text, profile)
        return 0.7

    def execute(self, context, **kwargs) -> str:
        return "ok"


class _InactiveSkill(BaseSkill):
    metadata = SkillMetadata(
        name="inactive",
        description="test",
        triggers=["test"],
        priority=1.0,
        category=SkillCategory.EXTERNAL,
        token_cost_estimate=50,
    )

    def activation_score(self, text: str, profile=None) -> float:
        _ = (text, profile)
        return 0.1

    def execute(self, context, **kwargs) -> str:
        return "ok"


class _ErrorSkill(BaseSkill):
    metadata = SkillMetadata(
        name="error_skill",
        description="test",
        triggers=["test"],
        priority=1.0,
        category=SkillCategory.MEMORY,
        token_cost_estimate=100,
    )

    def activation_score(self, text: str, profile=None) -> float:
        _ = (text, profile)
        raise RuntimeError("boom")

    def execute(self, context, **kwargs) -> str:
        return "ok"


def test_register_and_get_skill() -> None:
    registry = SkillRegistry()
    skill = _HighPrioritySkill()
    registry.register(skill)
    assert registry.get_skill("high_priority") is skill


# ----- two-stage scoring: rule floor → light-LLM rescue (stage 2) -----

_RESCUE_PROFILE = {"intent": "emotional_vent"}


class _GreySkill(BaseSkill):
    """Always scores below threshold — only the stage-2 rescue can activate it."""

    metadata = SkillMetadata(
        name="grey_skill",
        description="test grey",
        triggers=["test"],
        priority=1.0,
        category=SkillCategory.ANALYSIS,
        token_cost_estimate=100,
    )

    def activation_score(self, text: str, profile=None) -> float:
        _ = (text, profile)
        return 0.15

    def execute(self, context, **kwargs) -> str:
        return "ok"


class _StubLLM:
    """Minimal sync LLM stand-in: returns a canned reply or raises."""

    def __init__(self, reply: str = "", error: Exception | None = None) -> None:
        self.reply = reply
        self.error = error
        self.prompts: list[str] = []

    def invoke(self, prompt: str) -> object:
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        return self.reply

    async def ainvoke(self, prompt: str) -> object:
        return self.invoke(prompt)


def test_grey_skill_rescued_by_llm(activation_tracer) -> None:
    """Stage 2 rescues a rule miss: max(0.15, 0.8) clears the threshold."""
    registry = SkillRegistry(tracer=activation_tracer)
    registry.register(_GreySkill())
    llm = _StubLLM(reply='{"grey_skill": 0.8}')

    selected = registry.select_skills(
        "心里堵得慌，说不出的滋味", _RESCUE_PROFILE, token_budget=1000, llm=llm
    )
    assert [skill.metadata.name for skill in selected] == ["grey_skill"]
    assert len(llm.prompts) == 1

    record = activation_tracer.records[0]
    assert record.activated is True
    assert record.score == 0.8
    assert "source=llm_rescue" in record.reason
    assert "rule_score=0.15" in record.reason
    assert "llm_score=0.80" in record.reason


def test_grey_skill_llm_low_score_stays_suppressed(activation_tracer) -> None:
    """LLM below threshold cannot rescue: max(0.15, 0.2) stays under 0.3."""
    registry = SkillRegistry(tracer=activation_tracer)
    registry.register(_GreySkill())
    llm = _StubLLM(reply='{"grey_skill": 0.2}')

    selected = registry.select_skills("今天有点闷", _RESCUE_PROFILE, token_budget=1000, llm=llm)
    assert selected == []

    record = activation_tracer.records[0]
    assert record.activated is False
    assert record.score == 0.2
    assert "source=llm_rescue" in record.reason


def test_grey_skill_llm_failure_degrades_to_rules(activation_tracer) -> None:
    """LLM failure never breaks selection: grey skill keeps its rule outcome."""
    registry = SkillRegistry(tracer=activation_tracer)
    registry.register(_GreySkill())
    llm = _StubLLM(error=RuntimeError("timeout"))

    selected = registry.select_skills("今天有点闷", _RESCUE_PROFILE, token_budget=1000, llm=llm)
    assert selected == []

    record = activation_tracer.records[0]
    assert record.activated is False
    assert record.score == 0.15
    assert "source=rule" in record.reason
    assert "llm_rescue=error" in record.reason


def test_rule_activated_skills_never_call_llm() -> None:
    """Hot path: when rules clear the threshold the LLM is never invoked."""
    registry = SkillRegistry()
    registry.register(_HighPrioritySkill())
    registry.register(_LowPrioritySkill())
    llm = _StubLLM(reply="{}")

    selected = registry.select_skills("今天心情不好", _RESCUE_PROFILE, token_budget=1000, llm=llm)
    assert len(selected) == 2
    assert llm.prompts == []


def test_crisis_rule_hit_immune_to_llm_downgrade(activation_tracer) -> None:
    """Severe crisis signal scores 1.0 at rule stage — no LLM veto path."""
    from app.domain.skills.crisis_detector import CrisisDetectorSkill

    registry = SkillRegistry(tracer=activation_tracer)
    registry.register(CrisisDetectorSkill())
    registry.register(_GreySkill())
    llm = _StubLLM(reply='{"crisis_detector": 0.1, "grey_skill": 0.05}')

    selected = registry.select_skills("我不想活了", _RESCUE_PROFILE, token_budget=1000, llm=llm)
    assert "crisis_detector" in [skill.metadata.name for skill in selected]

    crisis_record = next(
        r for r in activation_tracer.records if r.skill_name == "crisis_detector"
    )
    assert crisis_record.score == 1.0
    assert crisis_record.activated is True
    assert "source=rule" in crisis_record.reason


def test_llm_none_keeps_pure_rule_behavior(activation_tracer) -> None:
    """llm=None (or omitted) is identical to the pre-two-stage pure-rule path."""
    registry = SkillRegistry(tracer=activation_tracer)
    registry.register(_HighPrioritySkill())
    registry.register(_GreySkill())

    selected = registry.select_skills("今天心情不好", _RESCUE_PROFILE, token_budget=1000)
    assert [skill.metadata.name for skill in selected] == ["high_priority"]

    record = activation_tracer.records[-1]
    assert record.skill_name == "grey_skill"
    assert record.activated is False
    assert record.score == 0.15
    assert "llm_rescue=no_llm" in record.reason


def test_non_rescue_intent_skips_llm_entirely() -> None:
    """casual_chat turns never spend rescue tokens even with an LLM present."""
    registry = SkillRegistry()
    registry.register(_GreySkill())
    llm = _StubLLM(reply='{"grey_skill": 0.99}')

    selected = registry.select_skills("随便聊聊", {"intent": "casual_chat"}, token_budget=1000, llm=llm)
    assert selected == []
    assert llm.prompts == []


def test_select_skills_orders_by_score_priority(activation_tracer) -> None:
    registry = SkillRegistry(tracer=activation_tracer)
    registry.register(_HighPrioritySkill())
    registry.register(_LowPrioritySkill())
    registry.register(_ExpensiveSkill())
    registry.register(_InactiveSkill())

    selected = registry.select_skills(
        "今天心情不好", {"intent": "emotional_support"}, token_budget=1000
    )
    names = [skill.metadata.name for skill in selected]
    assert names[0] == "high_priority"
    assert "inactive" not in names
    assert len(activation_tracer.records) == 4


def test_select_skills_respects_token_budget() -> None:
    registry = SkillRegistry()
    registry.register(_HighPrioritySkill())
    registry.register(_LowPrioritySkill())
    registry.register(_ExpensiveSkill())

    selected = registry.select_skills("简单记录", token_budget=250)
    total_cost = sum(skill.metadata.token_cost_estimate for skill in selected)
    assert total_cost <= 250
    assert "expensive" not in [skill.metadata.name for skill in selected]


def test_select_skills_records_suppressed_skills(activation_tracer) -> None:
    registry = SkillRegistry(tracer=activation_tracer)
    registry.register(_InactiveSkill())
    registry.select_skills("普通日记", token_budget=1000)

    record = activation_tracer.records[0]
    assert record.skill_name == "inactive"
    assert record.activated is False
    assert record.threshold == ACTIVATION_THRESHOLD


def test_select_skills_handles_activation_errors(activation_tracer) -> None:
    registry = SkillRegistry(tracer=activation_tracer)
    registry.register(_HighPrioritySkill())
    registry.register(_ErrorSkill())

    selected = registry.select_skills("测试", token_budget=1000)
    assert any(skill.metadata.name == "high_priority" for skill in selected)
    assert "error_skill" not in [skill.metadata.name for skill in selected]


def test_default_registry_has_two_mvp_skills() -> None:
    """Stub skills were removed; only CrisisDetector and Sentiment remain."""
    registry = create_default_registry()
    assert len(registry.skills) == 2
    assert "crisis_detector" in registry.skills
    assert "sentiment_skill" in registry.skills


def test_diary_registry_has_three_skills() -> None:
    """Diary registry adds memory_recall to crisis_detector + sentiment."""
    registry = create_diary_registry()
    assert len(registry.skills) == 3
    assert "crisis_detector" in registry.skills
    assert "sentiment_skill" in registry.skills
    assert "memory_recall" in registry.skills


def test_diary_registry_memory_recall_activates_on_retrospective() -> None:
    """Memory recall should activate for retrospective diary content."""
    registry = create_diary_registry()
    selected = registry.select_skills(
        "上周和朋友去了公园，很开心",
        {"intent": "retrospective_review"},
        token_budget=4000,
    )
    selected_names = {skill.metadata.name for skill in selected}
    assert "memory_recall" in selected_names


def test_chat_registry_has_four_skills() -> None:
    """Chat registry has crisis + sentiment + memory_recall + entity_tracker."""
    registry = create_chat_registry()
    assert len(registry.skills) == 4
    assert "crisis_detector" in registry.skills
    assert "sentiment_skill" in registry.skills
    assert "memory_recall" in registry.skills
    assert "entity_tracker" in registry.skills


def test_diary_registry_shares_skills_with_default() -> None:
    """Diary registry shares crisis_detector and sentiment_skill with default."""
    default_registry = create_default_registry()
    diary_registry = create_diary_registry()
    shared = set(default_registry.skills.keys()) & set(diary_registry.skills.keys())
    assert "crisis_detector" in shared
    assert "sentiment_skill" in shared


def test_no_stub_skills_registered() -> None:
    """Stub skills were removed in the dedup cleanup; verify they're gone."""
    registry = create_default_registry()
    selected = registry.select_skills(
        "今天完成了日常工作，天气不错。",
        {"intent": "pure_record"},
        token_budget=10000,
    )
    selected_names = {skill.metadata.name for skill in selected}
    stub_names = {
        "pattern_detector",
        "habit_tracker",
        "memory_reader",
        "memory_writer",
        "summary_generator",
        "search_diary_skill",
        "weather_skill",
        "address_skill",
    }
    assert selected_names.isdisjoint(stub_names)
