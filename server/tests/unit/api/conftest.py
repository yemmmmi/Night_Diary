"""Fixtures for API route tests."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app


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
        yield client
    get_settings.cache_clear()
