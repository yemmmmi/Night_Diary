"""Unit tests for model download service."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.config import Settings
from app.services.model_downloader import (
    ModelDownloadService,
    _mark_ready,
    configure_hf_environment,
    reset_model_download_service,
)


@pytest.fixture(autouse=True)
def _reset_service() -> None:
    reset_model_download_service()
    yield
    reset_model_download_service()


def test_configure_hf_environment_sets_cache_dirs(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("HF_HOME", raising=False)
    monkeypatch.delenv("SENTENCE_TRANSFORMERS_HOME", raising=False)
    monkeypatch.delenv("HF_ENDPOINT", raising=False)

    settings = Settings(data_dir=str(tmp_path), hf_endpoint="https://hf-mirror.com")
    configure_hf_environment(settings)

    assert (
        Path(settings.models_dir).resolve().as_posix()
        in Path(__import__("os").environ["HF_HOME"]).as_posix()
    )
    assert __import__("os").environ["HF_ENDPOINT"] == "https://hf-mirror.com"


def test_snapshot_marks_ready_when_marker_exists(tmp_path) -> None:
    settings = Settings(data_dir=str(tmp_path))
    _mark_ready(settings, "BAAI/bge-small-zh-v1.5")
    _mark_ready(settings, "BAAI/bge-reranker-base")

    service = ModelDownloadService(settings)
    snap = service.snapshot()

    assert snap.all_ready is True
    assert snap.overall_progress == 100.0


def test_start_download_invokes_snapshot_download(tmp_path) -> None:
    settings = Settings(data_dir=str(tmp_path))
    downloaded: list[str] = []

    def fake_snapshot_download(*, repo_id: str, cache_dir: str, resume_download: bool) -> str:
        downloaded.append(repo_id)
        return str(Path(cache_dir))

    service = ModelDownloadService(settings)
    with patch("huggingface_hub.snapshot_download", side_effect=fake_snapshot_download):
        assert service.start() is True
        service._thread.join(timeout=5)

    assert len(downloaded) == 2
    snap = service.snapshot()
    assert snap.all_ready is True
