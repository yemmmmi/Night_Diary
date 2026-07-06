"""Fixtures for API route tests."""

from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app


def _wait_for_bootstrap(client: TestClient, timeout_s: float = 30.0) -> None:
    """Wait until async sidecar bootstrap sets ``app.state.container``."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if getattr(client.app.state, "bootstrap_done", False):
            return
        time.sleep(0.05)
    raise TimeoutError("backend bootstrap did not complete")


@pytest.fixture()
def api_client(tmp_path) -> TestClient:
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
        yield client
    get_settings.cache_clear()


# ---- Auth helpers ----


def _register_and_login(
    client: TestClient,
    email: str = "alice@test.com",
    password: str = "password123",
    nickname: str = "Alice",
) -> tuple[str, dict]:
    """Register a user and return (token, user_dict)."""
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "nickname": nickname},
    )
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return body["access_token"], body["user"]


@pytest.fixture()
def auth_headers(api_client: TestClient) -> dict[str, str]:
    """Return Authorization headers for a default test user."""
    token, _ = _register_and_login(api_client)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def two_users(api_client: TestClient) -> tuple[dict[str, str], dict[str, str]]:
    """Register two users and return their auth headers."""
    token_a, _ = _register_and_login(
        api_client, email="alice@test.com", nickname="Alice"
    )
    token_b, _ = _register_and_login(
        api_client, email="bob@test.com", nickname="Bob"
    )
    return (
        {"Authorization": f"Bearer {token_a}"},
        {"Authorization": f"Bearer {token_b}"},
    )


@pytest.fixture()
def authed_client(api_client: TestClient) -> TestClient:
    """TestClient with auto-authentication via dependency override.

    Existing route tests use this instead of `api_client` to avoid
    passing auth headers on every request. Isolation tests that need
    real JWT auth or no-auth still use `api_client` directly.
    """
    from app.api.deps import get_current_user
    from app.infrastructure.models.user import UserRow

    _test_user = UserRow(
        id=1,
        email="route-test@test.com",
        nickname="Route Test",
        password_hash="dummy",
        is_active=True,
    )
    api_client.app.dependency_overrides[get_current_user] = lambda: _test_user
    yield api_client
    api_client.app.dependency_overrides.clear()
