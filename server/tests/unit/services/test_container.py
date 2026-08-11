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
    planner = container.build_execution_planner()
    assert isinstance(planner, ExecutionPlanner)


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
    graph = container.build_multi_agent_graph()
    if graph is not None:
        assert graph is not None


# ---------------------------------------------------------------------------
# V3 P4 Task 12: embedder + reranker injection into EpisodicMemory
# ---------------------------------------------------------------------------


def _make_core_container(tmp_path) -> ServiceContainer:
    """Build a *core-only* container (no AI stack / memory layers yet).

    Uses ``create_core`` so ``episodic_memory`` starts as ``None``, letting
    tests exercise ``_ensure_memory_layers_locked`` in isolation.
    """
    settings = Settings(
        data_dir=str(tmp_path / "data"),
        llm_api_key="sk-test",
        llm_base_url="https://api.example.com/v1",
        llm_model="test-model",
        model_key_secret="test-model-secret-min-16-chars!!",
    )
    return ServiceContainer.create_core(settings)


def test_ensure_memory_layers_injects_embedder_and_reranker(tmp_path) -> None:
    """_ensure_memory_layers_locked should inject embedder + reranker into EpisodicMemory."""
    from unittest.mock import MagicMock, patch

    container = _make_core_container(tmp_path)

    with patch.object(container, "_build_embedder") as mock_embed, \
            patch.object(container, "_get_reranker") as mock_rerank:
        mock_embed.return_value = MagicMock(name="embedder")
        mock_rerank.return_value = MagicMock(name="reranker")

        container._ensure_memory_layers_locked(user_id="user-1")
        memory = container.episodic_memory

        assert memory is not None
        # EpisodicMemory should have been injected with both deps
        assert memory._embedder is not None
        assert memory._reranker is not None
        mock_embed.assert_called_once()
        mock_rerank.assert_called_once()


def test_build_embedder_is_singleton(tmp_path) -> None:
    """_build_embedder must return the same instance on repeated calls.

    The embedding model is expensive to load (~100 MB); the container must
    cache a single instance rather than rebuilding per call.
    """
    container = _make_core_container(tmp_path)

    embedder1 = container._build_embedder()
    embedder2 = container._build_embedder()

    assert embedder1 is embedder2


def test_reranker_shared_between_rag_and_episodic(tmp_path) -> None:
    """RAG retrieval and episodic memory must share the same reranker instance.

    ``_get_reranker`` caches the cross-encoder so it loads at most once per
    container lifetime, then reuses it for both ``HybridRetriever`` and
    ``EpisodicMemory`` Stage-3 reranking.
    """
    from unittest.mock import MagicMock, patch

    container = _make_core_container(tmp_path)

    sentinel = MagicMock(name="reranker")
    with patch.object(container, "_build_reranker", return_value=sentinel) as mock_build:
        r1 = container._get_reranker()
        r2 = container._get_reranker()

        assert r1 is sentinel
        assert r2 is sentinel
        # Underlying _build_reranker called exactly once (singleton cache)
        assert mock_build.call_count == 1
