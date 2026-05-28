"""Settings smoke tests."""

from __future__ import annotations

import pytest

from app.config import Settings, get_settings


def test_settings_load_defaults_from_env() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.app_env == "test"
    assert "night_diary.db" in settings.database_url
    assert settings.port == 8000


def test_settings_database_url_derived_from_data_dir() -> None:
    from pathlib import Path

    get_settings.cache_clear()
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        data_dir="/tmp/nd",
    )
    assert Path(settings.data_dir) == Path("/tmp/nd")
    assert settings.database_url.endswith("night_diary.db")
    assert Path(settings.chroma_persist_dir).name == "chroma_data"
    assert Path(settings.models_dir).name == "models"


def test_settings_model_key_secret_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    """MODEL_KEY_SECRET can be empty (LLM API keys stored in plaintext if not set)."""
    monkeypatch.delenv("MODEL_KEY_SECRET", raising=False)
    get_settings.cache_clear()
    settings = Settings(_env_file=None, data_dir="/tmp/nd")  # type: ignore[call-arg]
    assert settings.model_key_secret == ""
