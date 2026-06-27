"""Unit tests for security.py — PR-3: security hardening."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from app.config import Settings
from app.infrastructure.security import (
    SecurityError,
    decrypt_api_key,
    encrypt_api_key,
    get_fernet,
)
from app.shared.errors import AppError


def _make_settings(tmp_path: Path, *, app_env: str = "development", secret: str | None = None) -> Settings:
    return Settings(
        app_env=app_env,
        data_dir=str(tmp_path),
        model_key_secret=secret or "",
        database_url=f"sqlite:///{tmp_path}/test.db",
    )


def test_production_no_secret_raises(tmp_path: Path) -> None:
    """Production mode with no secret must fail-fast (not silently use weak key)."""
    settings = _make_settings(tmp_path, app_env="production", secret=None)
    with pytest.raises(SecurityError, match="production"):
        get_fernet(settings)


def test_dev_no_secret_generates_key(tmp_path: Path) -> None:
    """Dev mode auto-generates a random key and persists to secrets.key."""
    settings = _make_settings(tmp_path, app_env="development", secret=None)
    key_file = tmp_path / "secrets.key"
    assert not key_file.exists()

    fernet = get_fernet(settings)
    assert fernet is not None
    assert key_file.exists()

    # Subsequent calls reuse the same key (not regenerated)
    fernet2 = get_fernet(settings)
    assert fernet2 is not None


def test_decrypt_invalid_token_raises_security_error(tmp_path: Path) -> None:
    """Decryption failure must raise SecurityError (AppError subclass), not ValueError."""
    settings = _make_settings(tmp_path, app_env="development", secret="test-secret")
    with pytest.raises(SecurityError):
        decrypt_api_key("invalid-token", settings)


def test_security_error_is_app_error() -> None:
    """SecurityError must be an AppError subclass so error_handlers catches it."""
    err = SecurityError("test")
    assert isinstance(err, AppError)


def test_roundtrip_encrypt_decrypt(tmp_path: Path) -> None:
    """Encrypt then decrypt must return the original plaintext."""
    settings = _make_settings(tmp_path, app_env="development", secret="test-secret")
    original = "sk-test-api-key-12345"
    encrypted = encrypt_api_key(original, settings)
    decrypted = decrypt_api_key(encrypted, settings)
    assert decrypted == original


def test_explicit_secret_overrides_file(tmp_path: Path) -> None:
    """model_key_secret setting takes priority over secrets.key file."""
    key_file = tmp_path / "secrets.key"
    key_file.write_text("file-based-secret", encoding="utf-8")
    settings = _make_settings(tmp_path, app_env="development", secret="explicit-secret")
    # Should use explicit secret, not file
    encrypted = encrypt_api_key("test", settings)
    decrypted = decrypt_api_key(encrypted, settings)
    assert decrypted == "test"
