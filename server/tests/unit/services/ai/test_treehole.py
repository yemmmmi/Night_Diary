"""Unit tests for the tree-hole analyzer (scene-1 short reply + digest)."""

from __future__ import annotations

import json
from datetime import date

import pytest

from app.services.ai.treehole import (
    MAX_REPLY_CHARS,
    classify_intent,
    detect_crisis,
    fallback_treehole,
    route_digest_type,
    run_treehole,
)
from app.shared.llm_factory import StubLLMClient

_DAY = date(2026, 8, 12)

_VALID_JSON = json.dumps(
    {
        "reply": "今天辛苦了，抱抱你。",
        "summary": "加班到很晚，对项目进度感到焦虑，和领导有过不愉快沟通。",
        "topics": ["加班", "项目", "领导关系"],
        "temporal_refs": [
            {"direction": "past", "date_hint": "昨天", "summary": "和妈妈吵架"},
            {"direction": "future", "date_hint": "下周五", "summary": "项目答辩"},
        ],
        "key_events": ["和领导争执", "得知项目延期"],
        "emotional_shifts": ["平静", "焦虑", "低落"],
        "relationships": [{"name": "李总", "relation": "领导", "sentiment": -0.6}],
        "conflicts": ["想推进项目但被否决"],
        "concerns": ["担心延期影响晋升"],
    },
    ensure_ascii=False,
)


# ── Router ──────────────────────────────────────────────────────────────


def test_route_simple_record_to_basic():
    assert route_digest_type("今天吃了火锅，看了电影。", "pure_record") == "basic"


def test_route_emotional_intent_to_complex():
    assert route_digest_type("今天心情很差。", "emotional_support") == "complex"


@pytest.mark.parametrize(
    "content",
    [
        "昨天和妈妈吵架了，今天还是很难过。",
        "下周五要项目答辩，很紧张。",
        "上周的项目失败了，这个月压力很大。",
    ],
)
def test_route_cross_day_reference_to_complex(content):
    """提及非当天事件 → complex（temporal_refs 信号）。"""
    assert route_digest_type(content, "pure_record") == "complex"


def test_route_long_content_to_complex():
    long = "今天发生了很多事。" * 40  # > 300 chars
    assert route_digest_type(long, "pure_record") == "complex"


def test_route_many_emotion_words_to_complex():
    assert (
        route_digest_type("焦虑、抑郁、失眠、崩溃，全都来了。", "pure_record") == "complex"
    )


# ── Crisis ──────────────────────────────────────────────────────────────


def test_detect_crisis_true_for_severe_content():
    assert detect_crisis("我不想活了") is True


def test_detect_crisis_false_for_safe_content():
    assert detect_crisis("今天天气不错") is False


# ── Classify (rule layer, zero LLM) ─────────────────────────────────────


@pytest.mark.asyncio
async def test_classify_intent_rule_layer_only():
    result = await classify_intent("今天吃了火锅，看了电影。")
    assert result.intent_category == "pure_record"
    assert result.confidence > 0


# ── run_treehole: LLM path ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_treehole_llm_path_builds_digest():
    """合法 JSON → 短回复 + 完整 digest（source=llm）。"""
    llm = StubLLMClient(reply=_VALID_JSON)
    outcome = await run_treehole(
        content="今天很焦虑，加班到很晚，项目延期了，和领导争执。",
        day=_DAY,
        llm=llm,
        diary_tags=["工作"],
    )

    assert outcome.source == "llm"
    assert outcome.reply == "今天辛苦了，抱抱你。"
    assert len(outcome.reply) <= MAX_REPLY_CHARS

    d = outcome.digest
    assert d.digest_type == "complex"  # LLM 提取出复杂字段 → 升级 complex
    assert d.date == _DAY
    assert d.diary.intent == "emotional_support"
    assert d.diary.summary.startswith("加班到很晚")
    assert d.diary.topics == ["加班", "项目", "领导关系"]
    assert len(d.diary.temporal_refs) == 2
    assert d.diary.temporal_refs[0].direction == "past"
    assert d.diary.temporal_refs[1].date_hint == "下周五"
    assert d.diary.key_events == ["和领导争执", "得知项目延期"]
    assert d.diary.conflicts == ["想推进项目但被否决"]
    assert d.diary.concerns == ["担心延期影响晋升"]
    assert d.diary.relationships[0].name == "李总"


@pytest.mark.asyncio
async def test_run_treehole_deterministic_fields_from_estimator():
    """确定性字段（emotion/mood）来自 EmotionEstimator，不依赖 LLM。"""
    llm = StubLLMClient(reply=_VALID_JSON)
    outcome = await run_treehole(
        content="今天真的很焦虑，加班到很晚。",
        day=_DAY,
        llm=llm,
    )
    assert outcome.digest.diary.emotion in ("焦虑", "negative", "neutral", "positive", "crisis")
    assert 0.0 <= outcome.digest.diary.mood <= 1.0


@pytest.mark.asyncio
async def test_run_treehole_llm_failure_falls_back_to_rules():
    """LLM 返回非 JSON → 模板兜底（source=rule），不抛异常。"""
    llm = StubLLMClient(reply="这不是 JSON")
    outcome = await run_treehole(
        content="今天吃了火锅。",
        day=_DAY,
        llm=llm,
    )

    assert outcome.source == "rule"
    assert outcome.reply  # 模板回复非空
    assert outcome.digest.digest_type == "basic"
    assert outcome.digest.diary.summary  # 规则摘要非空


@pytest.mark.asyncio
async def test_run_treehole_llm_raise_falls_back_to_rules():
    """LLM 抛异常 → 模板兜底，不抛异常。"""

    class _BoomLLM:
        model = "boom"

        async def ainvoke(self, prompt: str):  # type: ignore[no-untyped-def]
            raise RuntimeError("LLM down")

    outcome = await run_treehole(
        content="今天心情不错。",
        day=_DAY,
        llm=_BoomLLM(),  # type: ignore[arg-type]
    )
    assert outcome.source == "rule"


@pytest.mark.asyncio
async def test_run_treehole_cleans_oversized_reply():
    """超长 reply 被截断到 MAX_REPLY_CHARS。"""
    long_reply = json.dumps(
        {
            "reply": "今天辛苦了" + "，真的辛苦了" * 30,
            "summary": "x",
            "topics": [],
            "temporal_refs": [],
            "key_events": [],
            "emotional_shifts": [],
            "relationships": [],
            "conflicts": [],
            "concerns": [],
        },
        ensure_ascii=False,
    )
    llm = StubLLMClient(reply=long_reply)
    outcome = await run_treehole(
        content="随便写写。",
        day=_DAY,
        llm=llm,
    )
    assert len(outcome.reply) <= MAX_REPLY_CHARS + 1  # "…" 边界


# ── fallback_treehole ───────────────────────────────────────────────────


def test_fallback_treehole_basic_for_simple_content():
    outcome = fallback_treehole(
        content="今天吃了火锅。",
        day=_DAY,
        intent="pure_record",
        confidence=0.9,
        diary_tags=[],
    )
    assert outcome.source == "rule"
    assert outcome.reply == "记下了，今天也好好度过了。"
    assert outcome.digest.digest_type == "basic"


def test_fallback_treehole_complex_for_emotional_intent():
    outcome = fallback_treehole(
        content="今天很崩溃。",
        day=_DAY,
        intent="emotional_support",
        confidence=0.95,
        diary_tags=[],
    )
    assert outcome.digest.digest_type == "complex"
