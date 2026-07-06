"""Performance smoke checks for delivery verification."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture()
def smoke_client(tmp_path) -> TestClient:
    settings = Settings(
        data_dir=str(tmp_path / "data"),
        llm_api_key="sk-test",
        model_key_secret="test-model-secret-min-16-chars!!",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            if getattr(client.app.state, "bootstrap_done", False):
                break
            time.sleep(0.05)
        # Register a test user and obtain auth token
        client.post(
            "/api/v1/auth/register",
            json={"email": "smoke@test.com", "password": "password123", "nickname": "Smoke"},
        )
        resp = client.post(
            "/api/v1/auth/login",
            data={"username": "smoke@test.com", "password": "password123"},
        )
        assert resp.status_code == 200, resp.text
        token = resp.json()["access_token"]
        client.headers["Authorization"] = f"Bearer {token}"
        yield client


def test_health_responds_quickly(smoke_client: TestClient) -> None:
    start = time.perf_counter()
    response = smoke_client.get("/health")
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert response.status_code == 200
    assert elapsed_ms < 500, f"/health too slow: {elapsed_ms:.1f}ms"


def test_sqlite_diary_list_under_budget(smoke_client: TestClient) -> None:
    for index in range(5):
        smoke_client.post("/api/v1/diary/entries", json={"content": f"smoke {index}"})

    start = time.perf_counter()
    response = smoke_client.get("/api/v1/diary/entries")
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert response.status_code == 200
    assert len(response.json()) == 5
    assert elapsed_ms < 1000, f"diary list too slow: {elapsed_ms:.1f}ms"


def test_ready_after_bootstrap(smoke_client: TestClient) -> None:
    response = smoke_client.get("/ready")
    assert response.status_code == 200
