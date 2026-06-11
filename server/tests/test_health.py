"""Smoke tests for the FastAPI application scaffold."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.main import create_app


def _wait_for_core(client: TestClient, timeout_s: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        response = client.get("/ready")
        if response.status_code == 200:
            return
        time.sleep(0.05)
    raise TimeoutError("core bootstrap did not complete")


def test_health_returns_ok() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_ready_returns_ok_after_core_bootstrap() -> None:
    with TestClient(create_app()) as client:
        _wait_for_core(client)
        response = client.get("/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_ready_returns_503_while_bootstrapping() -> None:
    with TestClient(create_app()) as client:
        # Core bootstrap may finish before the first request on fast CI runners;
        # force bootstrapping state to test the /ready contract deterministically.
        client.app.state.bootstrap_done = False
        client.app.state.container = None

        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json()["status"] == "bootstrapping"


def test_openapi_schema_available() -> None:
    with TestClient(create_app()) as client:
        _wait_for_core(client)
        response = client.get("/openapi.json")
        assert response.status_code == 200
        assert response.json()["info"]["title"] == "night-diary-v2"
