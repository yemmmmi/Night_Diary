"""Unit tests for ServiceContainer wiring."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.config import Settings
from app.services.container import ServiceContainer
from app.services.ai.router import ExecutionPlanner


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
        analysis = analysis_service.trigger_analysis(db, entry.id, container)
        assert analysis.diary_id == entry.id
        assert analysis.execution_tier
    finally:
        db.close()
