"""模型配置缓存 — 避免每次 LLM 调用都查询数据库获取模型供应商配置。

模型供应商配置很少变更，但在每次 LLM 调用时都会读取。
此缓存以 5 分钟 TTL 存储配置。
"""

from __future__ import annotations

import logging
from typing import Any

from app.infrastructure.redis_client import cache_delete, cache_get, cache_set

logger = logging.getLogger(__name__)

MODEL_CONFIG_TTL = 300  # 5 分钟
MODEL_CONFIG_PREFIX = "model_config:"


def cache_model_config(user_id: str, config: dict[str, Any]) -> None:
    """缓存用户的模型供应商配置。"""
    cache_set(f"{MODEL_CONFIG_PREFIX}{user_id}", config, MODEL_CONFIG_TTL)


def get_cached_model_config(user_id: str) -> dict[str, Any] | None:
    """获取缓存的模型供应商配置。"""
    data = cache_get(f"{MODEL_CONFIG_PREFIX}{user_id}")
    return data if isinstance(data, dict) else None


def invalidate_model_config(user_id: str) -> None:
    """使用户的缓存模型配置失效（如配置更新后）。"""
    cache_delete(f"{MODEL_CONFIG_PREFIX}{user_id}")
