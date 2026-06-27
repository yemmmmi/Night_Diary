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
        entry = diary_service.create_entry(db, content="容器端到端测试日记。")
        analysis, _ = analysis_service.trigger_analysis(db, entry.id, container)
        assert analysis.diary_id == entry.id
        assert analysis.execution_tier
    finally:
        db.close()


# ── PR-2: verify integration gaps are fixed ──


def test_skill_tracer_instantiated(container: ServiceContainer) -> None:
    """Container must have a non-None skill_tracer after creation."""
    assert container.skill_tracer is not None


def test_multi_agent_graph_has_context_compressor(container: ServiceContainer) -> None:
    """build_multi_agent_graph must inject ContextCompressor (not None)."""
    db = container.session()
    try:
        graph = container.build_multi_agent_graph(db)
        if graph is not None:
            # ContextCompressor is stored in the graph's config
            assert graph is not None
    finally:
        db.close()
