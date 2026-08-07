"""Fixtures for end-to-end API flow tests."""

from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from tests.embedding_stub import patch_chroma_embedding_function


@pytest.fixture(autouse=True)
def _no_real_embedding_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """E2E tests never load the real embedding model (heavy ML deps absent)."""
    patch_chroma_embedding_function(monkeypatch)


def _wait_for_bootstrap(client: TestClient, timeout_s: float = 30.0) -> None:
    """Wait until async backend bootstrap sets ``app.state.container``."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if getattr(client.app.state, "bootstrap_done", False):
            return
        time.sleep(0.05)
    raise TimeoutError("backend bootstrap did not complete")


@pytest.fixture()
def e2e_client(tmp_path) -> TestClient:
    """Boot a full app against an isolated data dir and authenticate a user.

    The returned ``TestClient`` already carries a valid ``Authorization``
    header so tests can call protected endpoints directly. The pattern
    mirrors ``tests/unit/api/conftest.py::api_client`` but performs real
    JWT registration/login instead of a dependency override.
    """
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
