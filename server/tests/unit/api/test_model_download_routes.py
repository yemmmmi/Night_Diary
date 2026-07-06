"""API tests for model download routes."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from app.services.model_downloader import reset_model_download_service

# huggingface_hub is an optional dependency for model download.
pytest.importorskip("huggingface_hub")


def _client(tmp_path) -> TestClient:
    settings = Settings(
        data_dir=str(tmp_path / "data"),
        llm_api_key="sk-test",
        model_key_secret="test-model-secret-min-16-chars!!",
    )
    reset_model_download_service()
    get_settings.cache_clear()
    app = create_app(settings)
    return TestClient(app)


def test_download_status_pending(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/api/v1/models/download/status")
        assert response.status_code == 200
        body = response.json()
        assert body["all_ready"] is False
        assert len(body["items"]) == 2


def test_start_download_returns_accepted(tmp_path) -> None:
    def fake_snapshot_download(*, repo_id: str, cache_dir: str, resume_download: bool) -> str:
        return cache_dir

    with _client(tmp_path) as client:
        with patch("huggingface_hub.snapshot_download", side_effect=fake_snapshot_download):
            started = client.post("/api/v1/models/download/start")
            assert started.status_code == 202

            for _ in range(50):
                status = client.get("/api/v1/models/download/status")
                if status.json()["all_ready"]:
                    break
                time.sleep(0.05)

        assert status.status_code == 200
        assert status.json()["all_ready"] is True
