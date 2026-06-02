"""Unit tests for SkillRegistry."""

from __future__ import annotations

from app.domain.skills.base import ACTIVATION_THRESHOLD, BaseSkill
from app.domain.skills.registry import SkillRegistry, create_default_registry
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


def test_select_skills_orders_by_score_priority(activation_tracer) -> None:
    registry = SkillRegistry(tracer=activation_tracer)
    registry.register(_HighPrioritySkill())
    registry.register(_LowPrioritySkill())
    registry.register(_ExpensiveSkill())
    registry.register(_InactiveSkill())

    selected = registry.select_skills("今天心情不好", {"intent": "emotional_support"}, token_budget=1000)
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


def test_default_registry_has_ten_skills() -> None:
    registry = create_default_registry()
    assert len(registry.skills) == 10


def test_stub_skills_do_not_activate_on_neutral_text(activation_tracer) -> None:
    registry = create_default_registry(tracer=activation_tracer)
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
