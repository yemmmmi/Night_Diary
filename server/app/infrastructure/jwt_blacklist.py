"""JWT 黑名单 — 通过在令牌过期前撤销令牌来支持主动登出。

当用户登出时，其 JWT 被加入黑名单，TTL 等于令牌剩余有效期。
每次认证请求时，认证依赖项会检查黑名单。
"""

from __future__ import annotations

import logging

from app.infrastructure.redis_client import cache_get, cache_set

logger = logging.getLogger(__name__)

BLACKLIST_KEY_PREFIX = "jwt:blacklist:"


def blacklist_token(jti: str, remaining_seconds: int) -> None:
    """将 JWT ID 加入黑名单。"""
    if remaining_seconds <= 0:
        return
    cache_set(f"{BLACKLIST_KEY_PREFIX}{jti}", True, remaining_seconds)


def is_blacklisted(jti: str) -> bool:
    """检查 JWT ID 是否在黑名单中。"""
    return cache_get(f"{BLACKLIST_KEY_PREFIX}{jti}") is not None
