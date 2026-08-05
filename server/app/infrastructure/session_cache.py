"""会话上下文缓存 — 跨重启持久化 SessionContext。

在生产环境中（Redis 可用），会话状态可在服务器重启后存活。
在开发环境中（无 Redis），回退到 session_context.py 中的
进程内 _sessions 字典。
"""

from __future__ import annotations

import logging
from typing import Any

from app.infrastructure.redis_client import cache_delete, cache_delete_pattern, cache_get, cache_set

logger = logging.getLogger(__name__)

SESSION_TTL = 1800  # 30 分钟
SESSION_KEY_PREFIX = "session:"


def cache_session(conversation_id: str, session_data: dict[str, Any]) -> None:
    """缓存会话上下文。"""
    cache_set(f"{SESSION_KEY_PREFIX}{conversation_id}", session_data, SESSION_TTL)


def get_cached_session(conversation_id: str) -> dict[str, Any] | None:
    """获取缓存的会话上下文。"""
    data = cache_get(f"{SESSION_KEY_PREFIX}{conversation_id}")
    return data if isinstance(data, dict) else None


def delete_cached_session(conversation_id: str) -> None:
    """删除缓存的会话上下文。"""
    cache_delete(f"{SESSION_KEY_PREFIX}{conversation_id}")


def delete_all_sessions() -> None:
    """删除所有缓存的会话（如登出时）。"""
    cache_delete_pattern(f"{SESSION_KEY_PREFIX}*")
