"""Unit tests for ContextCompressor."""

from __future__ import annotations

from app.domain.agents.context_compressor import (
    ContextCompressor,
    is_low_density,
    prepare_compressed_history,
)
from app.shared.token_utils import estimate_tokens


def test_is_low_density_filters_greetings_and_short_text() -> None:
    assert is_low_density("早安") is True
    assert is_low_density("你好") is True
    assert is_low_density("今天工作很累，和同事发生了争执，心里特别委屈。") is False


def test_compress_keeps_query_relevant_entries() -> None:
    compressor = ContextCompressor(
        max_tokens=50, similarity=lambda q, c: 1.0 if "失眠" in c else 0.0
    )
    result = compressor.compress(
        "今天又失眠了，脑子里全是工作的事。",
        episodic=[
            {
                "event_summary": "连续三天失眠",
                "content": "连续三天失眠，凌晨两点才睡着，白天精神很差",
            },
            {
                "event_summary": "周末去爬山",
                "content": "周末去爬山，天气很好，心情不错，拍了好多照片",
            },
        ],
    )
    assert "失眠" in result
    assert "爬山" not in result


def test_compress_respects_token_budget() -> None:
    long_episodic = [
        {"event_summary": f"重要事件{i}", "content": "失眠焦虑压力" * 40} for i in range(10)
    ]
    compressor = ContextCompressor(max_tokens=200)
    result = compressor.compress("最近总是失眠。", episodic=long_episodic)
    assert estimate_tokens(result) <= 210  # allow minor jieba version variance


def test_compress_skips_low_density_entries() -> None:
    compressor = ContextCompressor(max_tokens=500)
    result = compressor.compress(
        "今天状态一般。",
        episodic=[
            {"event_summary": "早安", "content": "早安"},
            {"event_summary": "连续加班导致身心疲惫", "content": "连续加班导致身心疲惫，需要休息"},
        ],
    )
    assert "加班" in result
    assert "早安" not in result


def test_compress_summarizes_long_entries_without_llm() -> None:
    long_text = "今天发生了很多事情。" + "细节描述。" * 80
    compressor = ContextCompressor(max_tokens=800)
    result = compressor.compress(
        "回顾今天。",
        episodic=[{"event_summary": "长日记", "content": long_text}],
    )
    assert len(result) < len(long_text)
    assert estimate_tokens(result) <= 800


def test_prepare_compressed_history_from_state() -> None:
    state = {
        "diary_content": "我又失眠了。",
        "episodic_context": [
            {"event_summary": "上周也失眠", "content": "上周也失眠，整晚翻来覆去睡不着"}
        ],
    }
    update = prepare_compressed_history(state)
    assert "compressed_history" in update
    assert "失眠" in update["compressed_history"]


def test_prepare_compressed_history_empty_when_no_episodic() -> None:
    assert prepare_compressed_history({"diary_content": "今天很好。"}) == {}
