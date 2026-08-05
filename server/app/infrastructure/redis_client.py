"""Redis 客户端，优雅降级到内存缓存。

当未设置 REDIS_URL 或 Redis 不可达时，所有操作静默回退到
进程内字典。这使应用在开发环境中无需 Redis 即可运行，
同时在生产环境中获得缓存收益。
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
_fallback_cache: dict[str, tuple[Any, float]] = {}  # 键 -> (值, 过期时间)


def _init_redis() -> None:
    """如果设置了 REDIS_URL 则初始化 Redis 客户端。"""
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
    """从缓存获取值。未找到或已过期时返回 None。"""
    if _redis_available and _redis_client is not None:
        try:
            raw: Any = _redis_client.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as exc:
            logger.debug("Redis get failed for key=%s: %s", key, exc)
            return None
    # 内存回退
    entry = _fallback_cache.get(key)
    if entry is None:
        return None
    value, expire_at = entry
    if expire_at and time.time() > expire_at:
        _fallback_cache.pop(key, None)
        return None
    return value


def cache_set(key: str, value: Any, ttl_seconds: int = 300) -> None:
    """设置缓存值并指定 TTL。"""
    if _redis_available and _redis_client is not None:
        try:
            _redis_client.setex(key, ttl_seconds, json.dumps(value, default=str))
            return
        except Exception as exc:
            logger.debug("Redis set failed for key=%s: %s", key, exc)
    # 内存回退
    _fallback_cache[key] = (value, time.time() + ttl_seconds)


def cache_delete(key: str) -> None:
    """从缓存中删除键。"""
    if _redis_available and _redis_client is not None:
        try:
            _redis_client.delete(key)
            return
        except Exception:
            pass
    _fallback_cache.pop(key, None)


def cache_delete_pattern(pattern: str) -> None:
    """删除所有匹配模式的键（如 'session:*'）。"""
    if _redis_available and _redis_client is not None:
        try:
            keys: list[str] = list(_redis_client.keys(pattern))
            if keys:
                _redis_client.delete(*keys)
            return
        except Exception:
            pass
    # 内存模式：简单前缀匹配
    prefix = pattern.replace("*", "")
    to_delete = [k for k in _fallback_cache if k.startswith(prefix)]
    for k in to_delete:
        _fallback_cache.pop(k, None)


# 导入时初始化
_init_redis()
