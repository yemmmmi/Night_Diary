"""用于 LLM API 密钥静态加密的 Fernet 加密。"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets as _secrets
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.config import Settings, get_settings
from app.shared.errors import AppError

logger = logging.getLogger(__name__)


class SecurityError(AppError):
    """当安全相关操作失败时（如解密）抛出。"""

    def __init__(self, message: str) -> None:
        super().__init__(message=message, http_status=500)


def _derive_fernet_key(secret: str) -> bytes:
    """从口令派生稳定的 Fernet 密钥。"""
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _resolve_secret(settings: Settings) -> str:
    """解析加密密钥，具有环境感知的回退机制。

    优先级：
    1. ``model_key_secret`` 设置项（环境变量或配置）
    2. data_dir 下的 ``secrets.key`` 文件
    3. 开发环境：自动生成随机密钥并持久化到 ``secrets.key``
    4. 生产环境：**快速失败** — 不会静默使用弱密钥回退
    """
    if settings.model_key_secret:
        return settings.model_key_secret

    key_file = Path(settings.data_dir) / "secrets.key"
    if key_file.is_file():
        return key_file.read_text(encoding="utf-8").strip()

    if settings.app_env == "production":
        raise SecurityError(
            "No encryption secret configured in production. "
            "Set MODEL_KEY_SECRET env var or create secrets.key file."
        )

    # 开发/测试：自动生成强随机密钥
    generated = _secrets.token_urlsafe(32)
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_text(generated, encoding="utf-8")
    logger.info("Auto-generated encryption key at %s (development mode)", key_file)
    return generated


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
        raise SecurityError("API Key 解密失败，密钥可能已更换") from exc
