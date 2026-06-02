"""Verify the observability ORM tables create and round-trip via SQLite tracers."""

from __future__ import annotations

import pytest
from sqlalchemy import inspect

from app.infrastructure.agent_decision_logger import SqliteAgentDecisionLogger
from app.infrastructure.database import (
    create_db_engine,
    create_session_factory,
    init_db,
)
from app.infrastructure.llm_call_tracer import SqliteLLMCallTracer
from app.infrastructure.skill_activation_tracer import SqliteSkillActivationTracer
from app.shared.tracing import (
    AgentDecisionRecord,
    LLMCallRecord,
    SkillActivationRecord,
)


@pytest.fixture
def session_factory():  # type: ignore[no-untyped-def]
    engine = create_db_engine("sqlite:///:memory:")
    init_db(engine)
    return create_session_factory(engine), engine


def test_all_three_tables_are_created(session_factory) -> None:  # type: ignore[no-untyped-def]
    _factory, engine = session_factory
    tables = set(inspect(engine).get_table_names())
    assert {"llm_call_logs", "agent_decisions", "skill_activations"} <= tables


def test_llm_call_tracer_round_trip(session_factory) -> None:  # type: ignore[no-untyped-def]
    factory, _engine = session_factory
    tracer = SqliteLLMCallTracer(factory)
    tracer.record(
        LLMCallRecord(
            agent_name="empathy",
            call_type="generate",
            model="deepseek-chat",
            tier="light",
            decision_id="dec-1",
            tokens_in=600,
            tokens_out=280,
            latency_ms=1234.5,
        )
    )
    records = tracer.load_records(decision_id="dec-1")
    assert len(records) == 1
    assert records[0].agent_name == "empathy"
    assert records[0].tokens_out == 280


def test_agent_decision_logger_persists_skill_ids_json(session_factory) -> None:  # type: ignore[no-untyped-def]
    factory, _engine = session_factory
    logger = SqliteAgentDecisionLogger(factory)
    logger.record(
        AgentDecisionRecord(
            agent_name="supervisor",
            decision_type="skill_activation",
            diary_id="d01",
            intent="emotional_support",
            tier="medium",
            skill_ids=("crisis_detector", "sentiment_skill"),
            reasoning="two skills cleared threshold",
        )
    )
    records = logger.load_records(diary_id="d01")
    assert len(records) == 1
    assert records[0].skill_ids == ("crisis_detector", "sentiment_skill")
    assert records[0].intent == "emotional_support"


def test_skill_activation_tracer_still_works(session_factory) -> None:  # type: ignore[no-untyped-def]
    factory, _engine = session_factory
    tracer = SqliteSkillActivationTracer(factory)
    tracer.record(
        SkillActivationRecord(
            skill_name="crisis_detector",
            score=1.0,
            threshold=0.3,
            activated=True,
            reason="severe keyword",
            decision_id="dec-9",
        )
    )
    records = tracer.load_records(decision_id="dec-9")
    assert len(records) == 1
    assert records[0].activated is True
