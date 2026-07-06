"""Tests for SlotExtractor — task decomposition and slot filling."""

from __future__ import annotations

from app.domain.agents.slot_extractor import SlotExtractor

# ── Time range extraction tests ─────────────────────────────────────


def test_extract_today() -> None:
    extractor = SlotExtractor()
    result = extractor.extract("今天心情怎么样")
    assert result.time_range == "today"
    assert "今天" in result.time_expression


def test_extract_yesterday() -> None:
    extractor = SlotExtractor()
    result = extractor.extract("昨天的日记在哪")
    assert result.time_range == "yesterday"


def test_extract_last_week() -> None:
    extractor = SlotExtractor()
    result = extractor.extract("查一下上周的日记")
    assert result.time_range == "last_week"


def test_extract_this_month() -> None:
    extractor = SlotExtractor()
    result = extractor.extract("这个月有哪些开心的事")
    assert result.time_range == "this_month"


def test_extract_recent() -> None:
    extractor = SlotExtractor()
    result = extractor.extract("最近怎么样")
    assert result.time_range == "recent"


def test_extract_absolute_date() -> None:
    extractor = SlotExtractor()
    result = extractor.extract("2024年1月15日的日记")
    assert result.time_range == "absolute"


def test_extract_no_time() -> None:
    extractor = SlotExtractor()
    result = extractor.extract("心情不好")
    assert result.time_range == ""


# ── Emotion keywords tests ──────────────────────────────────────────


def test_extract_single_emotion() -> None:
    extractor = SlotExtractor()
    result = extractor.extract("今天很开心")
    assert "开心" in result.emotion_keywords


def test_extract_multiple_emotions() -> None:
    extractor = SlotExtractor()
    result = extractor.extract("既开心又焦虑")
    assert "开心" in result.emotion_keywords
    assert "焦虑" in result.emotion_keywords


def test_extract_no_emotion() -> None:
    extractor = SlotExtractor()
    result = extractor.extract("帮我查日记")
    assert result.emotion_keywords == []


# ── Operation type tests ────────────────────────────────────────────


def test_extract_search_operation() -> None:
    extractor = SlotExtractor()
    result = extractor.extract("查一下上周的日记")
    assert result.operation == "search"


def test_extract_analyze_operation() -> None:
    extractor = SlotExtractor()
    result = extractor.extract("分析一下我的情绪趋势")
    assert result.operation == "analyze"


def test_extract_ask_operation() -> None:
    extractor = SlotExtractor()
    result = extractor.extract("怎么办才好呢")
    assert result.operation == "ask"


def test_extract_write_operation() -> None:
    extractor = SlotExtractor()
    result = extractor.extract("帮我写一篇日记")
    assert result.operation == "write"


def test_extract_compare_operation() -> None:
    extractor = SlotExtractor()
    result = extractor.extract("对比这周和上周的心情")
    assert result.operation == "compare"


def test_extract_operation_from_intent() -> None:
    """Operation inferred from intent when no explicit keyword found."""
    extractor = SlotExtractor()
    result = extractor.extract("日记", intent="retrospective_query")
    assert result.operation == "search"


# ── Multi-task detection tests ─────────────────────────────────────


def test_multi_task_detected_with_then() -> None:
    extractor = SlotExtractor()
    result = extractor.extract("查上周日记然后分析情绪")
    assert result.is_multi_task is True
    assert len(result.sub_tasks) >= 2


def test_multi_task_detected_with_then_next() -> None:
    extractor = SlotExtractor()
    result = extractor.extract("先查日记接着分析情绪")
    assert result.is_multi_task is True


def test_multi_task_not_detected_single() -> None:
    extractor = SlotExtractor()
    result = extractor.extract("查一下上周的日记")
    assert result.is_multi_task is False
    assert result.sub_tasks == []


# ── Style constraint tests ──────────────────────────────────────────


def test_style_constraint_short() -> None:
    extractor = SlotExtractor()
    result = extractor.extract("简短一点回答")
    assert "short" in result.style_constraints


def test_style_constraint_detailed() -> None:
    extractor = SlotExtractor()
    result = extractor.extract("详细说说")
    assert "detailed" in result.style_constraints


def test_style_constraint_gentle() -> None:
    extractor = SlotExtractor()
    result = extractor.extract("用温和的语气说")
    assert "gentle" in result.style_constraints


def test_style_constraint_direct() -> None:
    extractor = SlotExtractor()
    result = extractor.extract("直接告诉我")
    assert "direct" in result.style_constraints


def test_style_constraint_none() -> None:
    extractor = SlotExtractor()
    result = extractor.extract("查日记")
    assert result.style_constraints == []


# ── Edge case tests ─────────────────────────────────────────────────


def test_empty_input() -> None:
    extractor = SlotExtractor()
    result = extractor.extract("")
    assert result.time_range == ""
    assert result.emotion_keywords == []
    assert result.operation == ""
    assert result.is_multi_task is False


def test_whitespace_only() -> None:
    extractor = SlotExtractor()
    result = extractor.extract("   ")
    assert result.time_range == ""


def test_combined_slots() -> None:
    """Multiple slots extracted from a single message."""
    extractor = SlotExtractor()
    result = extractor.extract("查上周的日记然后分析焦虑情绪，简短一点")
    assert result.time_range == "last_week"
    assert "焦虑" in result.emotion_keywords
    assert result.is_multi_task is True
    assert "short" in result.style_constraints


def test_slot_result_dataclass_fields() -> None:
    """Verify SlotResult has all expected fields."""
    extractor = SlotExtractor()
    result = extractor.extract("测试")
    assert hasattr(result, "time_range")
    assert hasattr(result, "time_expression")
    assert hasattr(result, "emotion_keywords")
    assert hasattr(result, "operation")
    assert hasattr(result, "is_multi_task")
    assert hasattr(result, "sub_tasks")
    assert hasattr(result, "style_constraints")
