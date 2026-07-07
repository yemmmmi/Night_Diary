"""Redis client with graceful fallback to in-memory caching.

When REDIS_URL is not set or Redis is unreachable, all operations silently
fall back to an in-process dict. This allows the app to run without Redis
in development while gaining caching benefits in production.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

_REDIS_URL = os.getenv("REDIS_URL", "")
_redis_client: Any = None
_redis_available = False
_fallback_cache: dict[str, tuple[Any, float]] = {}  # key -> (value, expire_at)


def _init_redis() -> None:
    """Initialize Redis client if REDIS_URL is set."""
    global _redis_client, _redis_available
    if not _REDIS_URL:
        return
    try:
        import redis

        _redis_client = redis.from_url(_REDIS_URL, decode_responses=True)
        _redis_client.ping()
        _redis_available = True
        logger.info(
            "Redis connected: %s",
            _REDIS_URL.split("@")[-1] if "@" in _REDIS_URL else "(local)",
        )
    except ImportError:
        logger.warning("redis package not installed; using in-memory fallback")
    except Exception as exc:
        logger.warning("Redis connection failed (%s); using in-memory fallback", exc)


def is_redis_available() -> bool:
    return _redis_available


def cache_get(key: str) -> Any:
    """Get a value from cache. Returns None if not found or expired."""
    if _redis_available and _redis_client is not None:
        try:
            raw: Any = _redis_client.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as exc:
            logger.debug("Redis get failed for key=%s: %s", key, exc)
            return None
    # In-memory fallback
    entry = _fallback_cache.get(key)
    if entry is None:
        return None
    value, expire_at = entry
    if expire_at and time.time() > expire_at:
        _fallback_cache.pop(key, None)
        return None
    return value


def cache_set(key: str, value: Any, ttl_seconds: int = 300) -> None:
    """Set a value in cache with TTL."""
    if _redis_available and _redis_client is not None:
        try:
            _redis_client.setex(key, ttl_seconds, json.dumps(value, default=str))
            return
        except Exception as exc:
            logger.debug("Redis set failed for key=%s: %s", key, exc)
    # In-memory fallback
    _fallback_cache[key] = (value, time.time() + ttl_seconds)


def cache_delete(key: str) -> None:
    """Delete a key from cache."""
    if _redis_available and _redis_client is not None:
        try:
            _redis_client.delete(key)
            return
        except Exception:
            pass
    _fallback_cache.pop(key, None)


def cache_delete_pattern(pattern: str) -> None:
    """Delete all keys matching a pattern (e.g. 'session:*')."""
    if _redis_available and _redis_client is not None:
        try:
            keys: list[str] = list(_redis_client.keys(pattern))
            if keys:
                _redis_client.delete(*keys)
            return
        except Exception:
            pass
    # In-memory: simple prefix match
    prefix = pattern.replace("*", "")
    to_delete = [k for k in _fallback_cache if k.startswith(prefix)]
    for k in to_delete:
        _fallback_cache.pop(k, None)


# Initialize on import
_init_redis()
