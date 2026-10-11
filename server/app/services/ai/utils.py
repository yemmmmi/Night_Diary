"""Pure helpers: cache check, diary result filtering, token extraction.

``extract_token_usage`` is canonicalised in :mod:`app.domain.agents.state` and
re-exported here for backward-compatible imports from the executor layer.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from app.domain.agents.state import extract_token_usage

__all__ = [
    "extract_token_usage",
    "filter_diary_results",
    "format_diary_result",
    "merge_token_info",
    "should_use_cache",
    "summarize_diary_results",
]


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


def merge_token_info(base: dict[str, int], extra: dict[str, int]) -> dict[str, int]:
    """Merge two token-info dicts, summing shared keys and keeping unique ones."""
    all_keys = set(base) | set(extra)
    return {key: base.get(key, 0) + extra.get(key, 0) for key in all_keys}


def summarize_diary_results(
    results: list[dict[str, Any]],
    *,
    max_items: int = 8,
) -> str:
    """Aggregate retrieval hits into one bounded conclusion (compound tool, A6).

    Filtering and aggregation happen here, inside the tool, so only the
    conclusion re-enters the model context — replacing a multi-round tool loop.
    """
    if not results:
        return "未找到匹配的历史日记。"

    dates = sorted({str(item.get("date", "")) for item in results if item.get("date")})
    span = f"{dates[0]} ~ {dates[-1]}" if dates else "日期未知"

    tag_counter: Counter[str] = Counter()
    for item in results:
        for tag in str(item.get("tags", "")).replace("，", ",").split(","):
            tag = tag.strip()
            if tag:
                tag_counter[tag] += 1

    lines = [f"共命中 {len(results)} 条日记，时间跨度 {span}。"]
    if tag_counter:
        top_tags = "、".join(f"{tag}({count})" for tag, count in tag_counter.most_common(5))
        lines.append(f"高频标签：{top_tags}")
    for item in results[:max_items]:
        lines.append(format_diary_result(item))
    if len(results) > max_items:
        lines.append(f"（仅展示前 {max_items} 条，其余已略）")
    return "\n".join(lines)
