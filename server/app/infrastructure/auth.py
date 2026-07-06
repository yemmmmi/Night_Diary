"""Authentication utilities: password hashing and JWT tokens.

Uses ``bcrypt`` for password hashing and ``PyJWT`` for token signing.
The JWT secret is resolved via the same priority chain as
``model_key_secret`` (env var → ``secrets.key`` file → dev auto-generate).
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

# Token URL must match the login route path.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def hash_password(plain: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a password against a bcrypt hash."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def resolve_jwt_secret(settings: Settings | None = None) -> str:
    """Resolve the JWT signing secret.

    Priority:
    1. ``jwt_secret_key`` setting (env var or config)
    2. Fall back to ``_resolve_secret`` (model_key_secret / secrets.key)
    """
    settings = settings or get_settings()
    if settings.jwt_secret_key:
        return settings.jwt_secret_key
    return _resolve_secret(settings)


def create_access_token(
    data: dict[str, Any],
    settings: Settings | None = None,
) -> str:
    """Create a JWT access token.

    ``data`` should contain at least ``{"sub": str(user_id)}``.
    Expiration is set based on ``jwt_expire_minutes``.
    """
    settings = settings or get_settings()
    to_encode = data.copy()
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=settings.jwt_expire_minutes)
    # ``jti`` (JWT ID) uniquely identifies a token so it can be blacklisted
    # on active logout; see ``app.infrastructure.jwt_blacklist``.
    to_encode.update({"exp": expire, "iat": now, "jti": str(uuid4())})
    secret = resolve_jwt_secret(settings)
    return jwt.encode(to_encode, secret, algorithm=settings.jwt_algorithm)


def decode_access_token(
    token: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Decode and verify a JWT access token.

    Raises ``jwt.PyJWTError`` on invalid/expired tokens.
    """
    settings = settings or get_settings()
    secret = resolve_jwt_secret(settings)
    return jwt.decode(token, secret, algorithms=[settings.jwt_algorithm])
