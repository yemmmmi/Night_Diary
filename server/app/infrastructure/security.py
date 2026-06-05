"""Fernet encryption for LLM API keys at rest."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.config import Settings, get_settings


def _derive_fernet_key(secret: str) -> bytes:
    """Derive a stable Fernet key from a passphrase."""
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _resolve_secret(settings: Settings) -> str:
    if settings.model_key_secret:
        return settings.model_key_secret
    key_file = Path(settings.data_dir) / "secrets.key"
    if key_file.is_file():
        return key_file.read_text(encoding="utf-8").strip()
    return "night-diary-local-dev-key"


def get_fernet(settings: Settings | None = None) -> Fernet:
    resolved = _resolve_secret(settings or get_settings())
    if len(resolved) == 44 and resolved.endswith("="):
        return Fernet(resolved.encode("utf-8"))
    return Fernet(_derive_fernet_key(resolved))


def encrypt_api_key(plain: str, settings: Settings | None = None) -> str:
    return get_fernet(settings).encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_api_key(token: str, settings: Settings | None = None) -> str:
    try:
        return get_fernet(settings).decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("API Key 解密失败，密钥可能已更换") from exc
