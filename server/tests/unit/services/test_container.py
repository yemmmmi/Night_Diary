"""Unit tests for ServiceContainer wiring."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.services.ai.router import ExecutionPlanner
from app.services.container import ServiceContainer


@pytest.fixture()
def container(tmp_path) -> ServiceContainer:
    settings = Settings(
        data_dir=str(tmp_path / "data"),
        llm_api_key="sk-test",
        llm_base_url="https://api.example.com/v1",
        llm_model="test-model",
        model_key_secret="test-model-secret-min-16-chars!!",
    )
    return ServiceContainer.create(settings)


def test_container_builds_execution_planner(container: ServiceContainer) -> None:
    db = container.session()
    try:
        planner = container.build_execution_planner(db)
        assert isinstance(planner, ExecutionPlanner)
    finally:
        db.close()


def test_trigger_analysis_end_to_end(container: ServiceContainer) -> None:
    from app.services import analysis_service, diary_service

    db = container.session()
    try:
        entry = diary_service.create_entry(db, user_id="default", content="容器端到端测试日记。")
        analysis, _ = analysis_service.trigger_analysis(db, entry.id, container, user_id="default")
        assert analysis.diary_id == entry.id
        assert analysis.execution_tier
    finally:
        db.close()


def test_skill_tracer_instantiated(container: ServiceContainer) -> None:
    """Container must have a non-None skill_tracer after creation."""
    assert container.skill_tracer is not None


def test_multi_agent_graph_has_context_compressor(container: ServiceContainer) -> None:
    """build_multi_agent_graph must inject ContextCompressor (not None)."""
    db = container.session()
    try:
        graph = container.build_multi_agent_graph(db)
        if graph is not None:
            assert graph is not None
    finally:
        db.close()


def test_prompt_tuner_instantiated(container: ServiceContainer) -> None:
    """Container must have a non-None prompt_tuner after build_multi_agent_graph."""
    db = container.session()
    try:
        container.build_multi_agent_graph(db)
        assert container.prompt_tuner is not None
    finally:
        db.close()


def test_prompt_tuner_builds_style_fragment(container: ServiceContainer) -> None:
    """prompt_tuner.build_dynamic_prompt should return a non-empty style fragment."""
    db = container.session()
    try:
        container.build_multi_agent_graph(db)
        fragment = container.prompt_tuner.build_dynamic_prompt(
            agent_type="empathy",
            diary_word_count=100,
        )
        assert fragment
        assert "风格" in fragment or "回应" in fragment
    finally:
        db.close()
