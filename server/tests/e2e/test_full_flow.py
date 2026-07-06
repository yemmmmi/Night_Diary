"""End-to-end API flow: diary CRUD → analysis → feedback."""

from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app


def _wait_for_bootstrap(client: TestClient, timeout_s: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if getattr(client.app.state, "bootstrap_done", False):
            return
        time.sleep(0.05)
    raise TimeoutError("backend bootstrap did not complete")


@pytest.fixture()
def e2e_client(tmp_path) -> TestClient:
    settings = Settings(
        data_dir=str(tmp_path / "data"),
        llm_api_key="sk-test",
        llm_base_url="https://api.example.com/v1",
        llm_model="test-model",
        model_key_secret="test-model-secret-min-16-chars!!",
    )
    os.environ["DATA_DIR"] = settings.data_dir
    get_settings.cache_clear()
    app = create_app(settings)
    with TestClient(app) as client:
        _wait_for_bootstrap(client)
        # Register a test user and obtain auth token
        client.post(
            "/api/v1/auth/register",
            json={"email": "e2e@test.com", "password": "password123", "nickname": "E2E"},
        )
        resp = client.post(
            "/api/v1/auth/login",
            data={"username": "e2e@test.com", "password": "password123"},
        )
        assert resp.status_code == 200, resp.text
        token = resp.json()["access_token"]
        client.headers["Authorization"] = f"Bearer {token}"
        yield client
    get_settings.cache_clear()


def test_diary_analysis_feedback_flow(e2e_client: TestClient) -> None:
    created = e2e_client.post(
        "/api/v1/diary/entries",
        json={"content": "E2E 流程测试: 今天心情不错。"},
    )
    assert created.status_code == 201
    diary_id = created.json()["id"]

    listed = e2e_client.get("/api/v1/diary/entries")
    assert listed.status_code == 200
    assert any(entry["id"] == diary_id for entry in listed.json())

    analysis = e2e_client.post(f"/api/v1/analysis/{diary_id}")
    assert analysis.status_code == 201
    analysis_id = analysis.json()["id"]
    assert analysis.json()["reply"]

    feedback = e2e_client.post(
        f"/api/v1/feedback/{analysis_id}",
        json={"feedback_type": "positive", "response_style": "empathetic"},
    )
    assert feedback.status_code == 201
    assert feedback.json()["analysis_id"] == analysis_id

    updated = e2e_client.put(
        f"/api/v1/diary/entries/{diary_id}",
        json={"content": "E2E 流程测试: 已更新内容。"},
    )
    assert updated.status_code == 200

    deleted = e2e_client.delete(f"/api/v1/diary/entries/{diary_id}")
    assert deleted.status_code == 204
