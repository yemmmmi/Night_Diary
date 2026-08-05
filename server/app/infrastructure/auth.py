"""认证工具：密码哈希与 JWT 令牌。

使用 ``bcrypt`` 进行密码哈希，使用 ``PyJWT`` 进行令牌签名。
JWT 密钥通过与 ``model_key_secret`` 相同的优先级链解析
（环境变量 → ``secrets.key`` 文件 → 开发环境自动生成）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import bcrypt
import jwt
from fastapi.security import OAuth2PasswordBearer

from app.config import Settings, get_settings
from app.infrastructure.security import _resolve_secret

# Token URL 必须与登录路由路径一致。
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def hash_password(plain: str) -> str:
    """使用 bcrypt 对密码进行哈希。"""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """对照 bcrypt 哈希验证密码。"""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def resolve_jwt_secret(settings: Settings | None = None) -> str:
    """解析 JWT 签名密钥。

    优先级：
    1. ``jwt_secret_key`` 设置项（环境变量或配置）
    2. 回退到 ``_resolve_secret``（model_key_secret / secrets.key）
    """
    settings = settings or get_settings()
    if settings.jwt_secret_key:
        return settings.jwt_secret_key
    return _resolve_secret(settings)


def create_access_token(
    data: dict[str, Any],
    settings: Settings | None = None,
) -> str:
    """创建 JWT 访问令牌。

    ``data`` 应至少包含 ``{"sub": str(user_id)}``。
    过期时间根据 ``jwt_expire_minutes`` 设置。
    """
    settings = settings or get_settings()
    to_encode = data.copy()
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=settings.jwt_expire_minutes)
    # ``jti``（JWT ID）唯一标识一个令牌，使其可在主动登出时
    # 加入黑名单；参见 ``app.infrastructure.jwt_blacklist``。
    to_encode.update({"exp": expire, "iat": now, "jti": str(uuid4())})
    secret = resolve_jwt_secret(settings)
    return jwt.encode(to_encode, secret, algorithm=settings.jwt_algorithm)


def decode_access_token(
    token: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """解码并验证 JWT 访问令牌。

    令牌无效/过期时抛出 ``jwt.PyJWTError``。
    """
    settings = settings or get_settings()
    secret = resolve_jwt_secret(settings)
    return jwt.decode(token, secret, algorithms=[settings.jwt_algorithm])
