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


# ── P2-A: important-people boost in retrieval ranking ──────────────────


def test_compress_boosts_entries_mentioning_important_people() -> None:
    """Entries mentioning boosted names outrank equally similar ones (P2-A)."""
    compressor = ContextCompressor(
        max_tokens=500, similarity=lambda q, c: 0.5  # uniform relevance
    )
    result = compressor.compress(
        "晚饭吃了什么，聊了什么",
        episodic=[
            {"event_summary": "独处的晚上", "content": "一个人吃了简餐，看了会儿书就早早休息了"},
            {
                "event_summary": "和小雨的晚饭",
                "content": "和小雨一起吃了晚饭，聊了很多最近的烦恼和打算",
            },
            {"event_summary": "加班的晚上", "content": "晚上加班改方案，回家路上买了个面包"},
        ],
        boost_terms=["小雨"],
    )

    assert result.split("\n---\n")[0].startswith("和小雨的晚饭")

    # Without boost terms the order is unchanged (all similarity ties):
    # stable sort keeps insertion order, so the plain entry stays first.
    baseline = compressor.compress(
        "晚饭吃了什么，聊了什么",
        episodic=[
            {"event_summary": "独处的晚上", "content": "一个人吃了简餐，看了会儿书就早早休息了"},
            {
                "event_summary": "和小雨的晚饭",
                "content": "和小雨一起吃了晚饭，聊了很多最近的烦恼和打算",
            },
        ],
    )
    assert baseline.split("\n---\n")[0].startswith("独处的晚上")


def test_important_people_names_extracts_from_profile() -> None:
    from app.domain.agents.context_compressor import _important_people_names

    state = {
        "long_term_profile": {
            "important_people": [{"name": "小雨"}, {"name": " 妈妈 "}, 42, {"name": ""}]
        }
    }
    assert _important_people_names(state) == ["小雨", "妈妈"]
    assert _important_people_names({}) == []
    assert _important_people_names({"long_term_profile": None}) == []


def test_prepare_compressed_history_lifts_important_people_entries() -> None:
    """The graph prep-step feeds profile people into the compressor.

    Query shares no tokens with either entry, so lexical similarity ties
    at zero for both — only the people boost can lift 小雨's entry first.
    """
    state = {
        "diary_content": "最近过得怎么样",
        "episodic_context": [
            {"event_summary": "独处的晚上", "content": "一个人吃了简餐，看了会儿书就早早休息了"},
            {
                "event_summary": "和小雨的晚饭",
                "content": "和小雨一起吃了晚饭，聊了很多最近的烦恼和打算",
            },
        ],
        "long_term_profile": {"important_people": [{"name": "小雨"}]},
    }
    update = prepare_compressed_history(state)
    assert update["compressed_history"].split("\n---\n")[0].startswith("和小雨的晚饭")
