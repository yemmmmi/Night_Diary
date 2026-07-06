"""Session context cache -- persists SessionContext across restarts.

In production (Redis available), session state survives server restarts.
In development (no Redis), falls back to the in-process _sessions dict
in session_context.py.
"""

from __future__ import annotations

import logging
from typing import Any

from app.infrastructure.redis_client import cache_delete, cache_delete_pattern, cache_get, cache_set

logger = logging.getLogger(__name__)

SESSION_TTL = 1800  # 30 minutes
SESSION_KEY_PREFIX = "session:"


def cache_session(conversation_id: str, session_data: dict[str, Any]) -> None:
    """Cache a session context."""
    cache_set(f"{SESSION_KEY_PREFIX}{conversation_id}", session_data, SESSION_TTL)


def get_cached_session(conversation_id: str) -> dict[str, Any] | None:
    """Get a cached session context."""
    return cache_get(f"{SESSION_KEY_PREFIX}{conversation_id}")


def delete_cached_session(conversation_id: str) -> None:
    """Delete a cached session context."""
    cache_delete(f"{SESSION_KEY_PREFIX}{conversation_id}")


def delete_all_sessions() -> None:
    """Delete all cached sessions (e.g. on logout)."""
    cache_delete_pattern(f"{SESSION_KEY_PREFIX}*")
