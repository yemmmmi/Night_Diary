"""Settings smoke tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings


def test_settings_load_defaults_from_env() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.app_env == "test"
    assert settings.allowed_origins == ["http://localhost:5173"]


def test_settings_fail_without_required_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """`JWT_SECRET_KEY` and `MODEL_KEY_SECRET` are required, no fallback."""
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    monkeypatch.delenv("MODEL_KEY_SECRET", raising=False)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./test.db")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]
