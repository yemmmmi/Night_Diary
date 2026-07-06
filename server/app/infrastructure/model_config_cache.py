"""Model configuration cache -- avoids DB queries for model provider config.

Model provider configs change rarely but are read on every LLM call.
This cache stores them with a 5-minute TTL.
"""

from __future__ import annotations

import logging
from typing import Any

from app.infrastructure.redis_client import cache_delete, cache_get, cache_set

logger = logging.getLogger(__name__)

MODEL_CONFIG_TTL = 300  # 5 minutes
MODEL_CONFIG_PREFIX = "model_config:"


def cache_model_config(user_id: str, config: dict[str, Any]) -> None:
    """Cache a user's model provider config."""
    cache_set(f"{MODEL_CONFIG_PREFIX}{user_id}", config, MODEL_CONFIG_TTL)


def get_cached_model_config(user_id: str) -> dict[str, Any] | None:
    """Get a cached model provider config."""
    return cache_get(f"{MODEL_CONFIG_PREFIX}{user_id}")


def invalidate_model_config(user_id: str) -> None:
    """Invalidate cached model config for a user (e.g. after config update)."""
    cache_delete(f"{MODEL_CONFIG_PREFIX}{user_id}")
