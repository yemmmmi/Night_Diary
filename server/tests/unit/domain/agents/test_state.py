"""Unit tests for MultiAgentState reducers and token-usage extraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.domain.agents.state import extract_token_usage, merge_unique


def test_merge_unique_dedups_preserving_order() -> None:
    assert merge_unique(["empathy"], ["retrieval", "empathy"]) == ["empathy", "retrieval"]


def test_merge_unique_empty_sides() -> None:
    assert merge_unique([], ["a"]) == ["a"]
    assert merge_unique(["a"], []) == ["a"]


@dataclass
class _Resp:
    response_metadata: dict[str, Any]


def test_extract_token_usage_reads_metadata() -> None:
    resp = _Resp(
        response_metadata={
            "token_usage": {
                "total_tokens": 880,
                "completion_tokens": 280,
                "prompt_cache_hit_tokens": 400,
                "prompt_cache_miss_tokens": 200,
            }
        }
    )
    usage = extract_token_usage(resp)
    assert usage["total_tokens_used"] == 880
    assert usage["output_tokens"] == 280
    assert usage["cache_hit_tokens"] == 400
    assert usage["cache_miss_tokens"] == 200


def test_extract_token_usage_handles_missing_metadata() -> None:
    usage = extract_token_usage("a plain string with no metadata")
    assert usage == {
        "total_tokens_used": 0,
        "cache_hit_tokens": 0,
        "cache_miss_tokens": 0,
        "output_tokens": 0,
    }
