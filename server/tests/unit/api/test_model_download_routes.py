"""API tests for model download routes."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from app.services.model_downloader import (
    get_model_download_service,
    reset_model_download_service,
)

# huggingface_hub is an optional dependency for model download.
pytest.importorskip("huggingface_hub")


def _client(tmp_path) -> TestClient:
    settings = Settings(
        data_dir=str(tmp_path / "data"),
        llm_api_key="sk-test",
        model_key_secret="test-model-secret-min-16-chars!!",
    )
    reset_model_download_service()
    # 用测试的 settings 初始化服务单例——服务默认用全局 get_settings()
    # （默认 data_dir 可能含真实模型缓存导致 all_ready 误判），必须显式注入。
    get_model_download_service(settings)
    get_settings.cache_clear()
    app = create_app(settings)
    return TestClient(app)


def _wait_for_bootstrap(client: TestClient, timeout_s: float = 20.0) -> None:
    """等待 core bootstrap 完成，避免 TestClient 退出与后台引导线程竞态。"""
    import time

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if getattr(client.app.state, "bootstrap_done", False):
            return
        time.sleep(0.05)
    raise TimeoutError("backend bootstrap did not complete")


def test_download_status_pending(tmp_path) -> None:
    with _client(tmp_path) as client:
        _wait_for_bootstrap(client)
        response = client.get("/api/v1/models/download/status")
        assert response.status_code == 200
        body = response.json()
        assert body["all_ready"] is False
        assert len(body["items"]) == 2


def test_start_download_returns_accepted(tmp_path) -> None:
    def fake_snapshot_download(*, repo_id: str, cache_dir: str, resume_download: bool) -> str:
        return cache_dir

    with _client(tmp_path) as client:
        _wait_for_bootstrap(client)
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
