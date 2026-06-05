"""Verify per-tier model selection and llm_call_logs tracing."""

from __future__ import annotations

from unittest.mock import patch

from app.services import model_service
from app.services.ai.router import ExecutionPlanner, resolve_llm_clients_by_tier
from app.shared.llm_factory import LLMFactory, StubLLMClient
from app.shared.tracing import InMemoryLLMCallTracer
from app.shared.tracing_llm import TracingLLMClient


def test_resolve_llm_clients_by_tier_maps_active_providers(db_session) -> None:
    tracer = InMemoryLLMCallTracer()
    factory = LLMFactory()

    with patch.object(model_service, "validate_model_connection", return_value=None):
        model_service.create_model(
            db_session,
            model_name="light-model",
            api_key="sk-light",
            base_url="https://api.example.com/v1",
            tier="light",
            is_active=True,
        )
        model_service.create_model(
            db_session,
            model_name="heavy-model",
            api_key="sk-heavy",
            base_url="https://api.example.com/v1",
            tier="heavy",
            is_active=True,
        )

    clients = resolve_llm_clients_by_tier(db_session, llm_factory=factory, tracer=tracer)
    assert "light" in clients
    assert "heavy" in clients
    assert isinstance(clients["light"], TracingLLMClient)
    assert clients["light"].model == "light-model"
    assert clients["heavy"].model == "heavy-model"


def test_chain_execution_records_tier_model_in_tracer() -> None:
    tracer = InMemoryLLMCallTracer()
    light = TracingLLMClient(StubLLMClient(model="light-model"), model="light-model", tier="light", tracer=tracer)
    heavy = TracingLLMClient(StubLLMClient(model="heavy-model"), model="heavy-model", tier="heavy", tracer=tracer)

    planner = ExecutionPlanner(
        llm_by_tier={"light": light, "heavy": heavy},
        multi_agent_enabled=False,
    )
    planner.execute(
        diary_id=1,
        context={
            "current_content": "今天很好。",
            "tags_context": "（未设置标签）",
            "history_summary": "（暂无历史记录）",
            "weather_info": "晴",
        },
        content="今天很好。",
    )

    assert len(tracer.records) == 1
    assert tracer.records[0].model == "light-model"
    assert tracer.records[0].tier == "light"


def test_planner_prefers_tier_specific_client_over_default() -> None:
    light = StubLLMClient(model="light-only")
    default = StubLLMClient(model="default-fallback")
    planner = ExecutionPlanner(
        llm_by_tier={"light": light, "default": default},
        multi_agent_enabled=False,
    )
    planner.execute(
        diary_id=2,
        context={
            "current_content": "晴。",
            "tags_context": "",
            "history_summary": "",
            "weather_info": "",
        },
        content="晴。",
    )
    assert light.prompts
    assert not default.prompts
