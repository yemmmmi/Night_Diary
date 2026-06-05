"""Pure helpers: cache check, diary result filtering, token extraction."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def should_use_cache(
    last_time: datetime | None,
    now: datetime,
    *,
    threshold_minutes: int = 30,
) -> bool:
    if last_time is None:
        return False
    return (now - last_time).total_seconds() < threshold_minutes * 60


def filter_diary_results(
    results: list[dict[str, Any]],
    *,
    start_date: str = "",
    end_date: str = "",
    tag: str = "",
) -> list[dict[str, Any]]:
    filtered = results
    if start_date:
        filtered = [item for item in filtered if item.get("date", "") >= start_date]
    if end_date:
        filtered = [item for item in filtered if item.get("date", "") <= end_date]
    if tag:
        filtered = [item for item in filtered if tag in item.get("tags", "")]
    return filtered


def format_diary_result(item: dict[str, Any]) -> str:
    date_str = item.get("date", "未知日期")
    content = item.get("content", "")
    tags = item.get("tags", "")
    snippet = content[:150] + "..." if len(content) > 150 else content
    tag_part = f" {tags}" if tags else ""
    return f"[{date_str}]{tag_part} {snippet}"


def extract_token_usage(response: Any) -> dict[str, int]:
    usage: dict[str, Any] = {}
    if hasattr(response, "response_metadata"):
        usage = response.response_metadata.get("token_usage", {})
    elif isinstance(response, dict):
        usage = response.get("token_usage", {})

    return {
        "total_tokens": int(usage.get("total_tokens", 0)),
        "cache_hit_tokens": int(usage.get("prompt_cache_hit_tokens", 0)),
        "cache_miss_tokens": int(usage.get("prompt_cache_miss_tokens", 0)),
        "output_tokens": int(usage.get("completion_tokens", 0)),
    }


def merge_token_info(base: dict[str, int], extra: dict[str, int]) -> dict[str, int]:
    return {key: base.get(key, 0) + extra.get(key, 0) for key in base}
