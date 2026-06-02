"""Unit tests for CrisisDetectorSkill."""

from __future__ import annotations

from app.domain.skills.crisis_detector import CrisisDetectorSkill
from app.domain.skills.registry import create_default_registry


def test_crisis_text_activates_skill() -> None:
    skill = CrisisDetectorSkill()
    assert skill.can_activate("我不想活了，觉得一切都没有意义。") is True
    assert skill.activation_score("我不想活了") == 1.0


def test_normal_text_does_not_force_activation() -> None:
    skill = CrisisDetectorSkill()
    assert skill.can_activate("今天完成了项目，心情还不错。") is False


def test_execute_returns_resources_for_crisis_text() -> None:
    skill = CrisisDetectorSkill()
    result = skill.execute({"diary_content": "我不想活了，撑不下去了。", "user_id": "default"})
    assert "升级响应协议已触发" in result
    assert "400-161-9995" in result


def test_default_registry_selects_crisis_detector_for_crisis_text() -> None:
    registry = create_default_registry()
    selected = registry.select_skills("我不想活了", token_budget=1000)
    assert any(skill.metadata.name == "crisis_detector" for skill in selected)
