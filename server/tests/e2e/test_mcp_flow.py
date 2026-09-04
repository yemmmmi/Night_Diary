"""E2E: MCP stdio server through the real Dev API (registry → API → log)."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SCRIPT = Path(__file__).parents[1] / "fixtures" / "fake_mcp_stdio.py"


def _wait_ready(client: TestClient, timeout_s: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if client.get("/api/v1/dev/middleware-status").status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.2)
    raise TimeoutError("app bootstrap timed out")


@pytest.fixture()
def mcp_client(tmp_path):
    from app.config import Settings, get_settings
    from app.main import create_app

    mcp_stdios = f"fake:{sys.executable} {SCRIPT}"
    settings = Settings(
        data_dir=str(tmp_path / "data"),
        llm_api_key="sk-test",
        llm_base_url="https://api.example.com/v1",
        llm_model="test-model",
        model_key_secret="test-model-secret-min-16-chars!!",
        database_url_env="",
        mcp_stdios=mcp_stdios,
    )
    os.environ["DATA_DIR"] = settings.data_dir
    os.environ["DATABASE_URL"] = ""
    # Bootstrap builds the container via get_settings() (env vars), so the
    # stdio spec must also be exported for the registry to see it.
    os.environ["MCP_STDIOS"] = mcp_stdios
    get_settings.cache_clear()
    app = create_app(settings)
    with TestClient(app) as client:
        _wait_ready(client)
        yield client
    get_settings.cache_clear()
    os.environ.pop("MCP_STDIOS", None)


def test_stdio_endpoint_visible_and_callable(mcp_client: TestClient) -> None:
    status = mcp_client.get("/api/v1/dev/mcp/status")
    assert status.status_code == 200
    items = status.json()["items"]
    assert len(items) == 1
    assert items[0]["alias"] == "fake"
    assert items[0]["state"] == "healthy"
    assert items[0]["tool_count"] == 2

    tools = mcp_client.get("/api/v1/dev/mcp/tools")
    names = [t["name"] for t in tools.json()["items"]]
    assert "mcp__fake__echo" in names
    assert "search_diary" in names  # 本地工具同列
