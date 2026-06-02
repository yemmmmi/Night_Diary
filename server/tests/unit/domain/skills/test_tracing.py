"""Unit tests for skill activation tracing."""

from __future__ import annotations

from app.domain.skills.registry import create_default_registry
from app.shared.tracing import SkillActivationRecord


def test_sqlite_tracer_persists_records(sqlite_activation_tracer) -> None:
    sqlite_activation_tracer.record(
        SkillActivationRecord(
            skill_name="crisis_detector",
            score=1.0,
            threshold=0.3,
            activated=True,
            reason="test",
            decision_id="dec-1",
            input_digest="我不想活了",
        )
    )
    records = sqlite_activation_tracer.load_records(decision_id="dec-1")
    assert len(records) == 1
    assert records[0].skill_name == "crisis_detector"
    assert records[0].activated is True


def test_registry_writes_traces_for_all_skills(sqlite_activation_tracer) -> None:
    registry = create_default_registry(tracer=sqlite_activation_tracer)
    registry.select_skills("今天完成了工作。", token_budget=5000)
    records = sqlite_activation_tracer.load_records()
    assert len(records) == 10
