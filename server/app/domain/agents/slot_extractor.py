"""SlotExtractor — structured slot filling for scene-2 task decomposition.

Sits after ChatIntentClassifier in the conversation pipeline. Its job is to
extract structured slots (time range, emotion keywords, operation type) from
user input to support:

1. **Slot filling**: extract time ranges, emotion keywords, and operation
   types from free-text queries.
2. **Multi-task detection**: detect when a single message contains multiple
   tasks ("查上周日记然后分析情绪" → 2 tasks).
3. **Constraint identification**: detect user-expressed preferences
   ("简短一点", "用温和的语气") that constrain the response.

All operations are zero-token (pure regex/keyword matching) — no LLM calls.
The extractor is intentionally lightweight; complex semantic understanding
is handled by downstream components.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── Time range patterns ─────────────────────────────────────────────

# Relative time expressions
_RELATIVE_TIME_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"今天|今日|今天"), "today"),
    (re.compile(r"昨天|昨日"), "yesterday"),
    (re.compile(r"前天"), "day_before_yesterday"),
    (re.compile(r"明天|明日"), "tomorrow"),
    (re.compile(r"这周|本周"), "this_week"),
    (re.compile(r"上周|上个星期"), "last_week"),
    (re.compile(r"下周|下个星期"), "next_week"),
    (re.compile(r"这个月|本月"), "this_month"),
    (re.compile(r"上个月|上个礼月"), "last_month"),
    (re.compile(r"最近"), "recent"),
]

# Absolute date patterns (YYYY-MM-DD, MM月DD日)
_ABSOLUTE_DATE_RE = re.compile(r"(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?|\d{1,2}月\d{1,2}日)")

# ── Emotion keywords ────────────────────────────────────────────────

_EMOTION_KEYWORDS = [
    "开心",
    "快乐",
    "高兴",
    "兴奋",
    "愉快",
    "满足",
    "幸福",
    "难过",
    "伤心",
    "悲伤",
    "失落",
    "孤独",
    "寂寞",
    "生气",
    "愤怒",
    "烦躁",
    "恼火",
    "不满",
    "焦虑",
    "紧张",
    "担心",
    "害怕",
    "恐惧",
    "不安",
    "平静",
    "放松",
    "释然",
    "淡然",
    "疲惫",
    "累",
    "困",
    "无力",
    "空虚",
    "感动",
    "感恩",
    "温暖",
    "心疼",
]

# ── Operation types ─────────────────────────────────────────────────

_OPERATION_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "search": [
        re.compile(r"查|找|搜索|检索|看看|查看|回顾"),
    ],
    "analyze": [
        re.compile(r"分析|评估|总结|归纳|复盘"),
    ],
    "compare": [
        re.compile(r"对比|比较|区别|差异"),
    ],
    "write": [
        re.compile(r"写|记录|记下|帮我写"),
    ],
    "ask": [
        re.compile(r"怎么办|怎么样|如何|为什么|能不能|可以吗|建议|推荐"),
    ],
}

# ── Multi-task connectors ───────────────────────────────────────────

_MULTI_TASK_CONNECTORS = ["然后", "接着", "再", "之后", "最后", "并且"]

# ── Constraint patterns ─────────────────────────────────────────────

# Response style constraints
_STYLE_CONSTRAINTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"简短(一点|些)?|简单(一点|些)?|少说"), "short"),
    (re.compile(r"详细(一点|些)?|具体(一点|些)?|多说"), "detailed"),
    (re.compile(r"温和|温柔|轻声"), "gentle"),
    (re.compile(r"直接|直白|坦率"), "direct"),
    (re.compile(r"正式|严谨"), "formal"),
    (re.compile(r"轻松|随意|口语"), "casual"),
]


@dataclass
class SlotResult:
    """Result of slot extraction."""

    time_range: str = ""  # today/yesterday/this_week/last_week/absolute_date
    time_expression: str = ""  # Original matched text
    emotion_keywords: list[str] = field(default_factory=list)
    operation: str = ""  # search/analyze/compare/write/ask
    is_multi_task: bool = False
    sub_tasks: list[str] = field(default_factory=list)
    style_constraints: list[str] = field(default_factory=list)  # short/detailed/gentle/...


class SlotExtractor:
    """Extract structured slots from user input.

    Zero-token, rule-based extraction. Designed to run after intent
    classification and before context assembly.

    Usage::

        extractor = SlotExtractor()
        slots = extractor.extract("查一下上周的日记然后分析情绪", intent="retrospective_query")
        if slots.is_multi_task:
            # Handle multi-task decomposition
            for sub_task in slots.sub_tasks:
                ...
    """

    def extract(self, content: str, *, intent: str = "") -> SlotResult:
        """Extract structured slots from user input.

        Args:
            content: Preprocessed user input.
            intent: Intent category from ChatIntentClassifier (optional context).

        Returns:
            SlotResult with extracted slots.
        """
        if not content or not content.strip():
            return SlotResult()

        result = SlotResult()

        # 1. Time range extraction
        result.time_range, result.time_expression = self._extract_time_range(content)

        # 2. Emotion keywords extraction
        result.emotion_keywords = self._extract_emotion_keywords(content)

        # 3. Operation type extraction
        result.operation = self._extract_operation(content, intent)

        # 4. Multi-task detection
        result.is_multi_task, result.sub_tasks = self._detect_multi_task(content)

        # 5. Style constraint identification
        result.style_constraints = self._extract_style_constraints(content)

        logger.debug(
            "slot.extract intent=%s time=%s emotion=%s op=%s multi=%s constraints=%s",
            intent,
            result.time_range,
            result.emotion_keywords,
            result.operation,
            result.is_multi_task,
            result.style_constraints,
        )

        return result

    def _extract_time_range(self, content: str) -> tuple[str, str]:
        """Extract time range from content.

        Returns (time_range_label, original_expression).
        """
        # Check relative time patterns first
        for pattern, label in _RELATIVE_TIME_PATTERNS:
            match = pattern.search(content)
            if match:
                return label, match.group()

        # Check absolute date patterns
        match = _ABSOLUTE_DATE_RE.search(content)
        if match:
            return "absolute", match.group()

        return "", ""

    def _extract_emotion_keywords(self, content: str) -> list[str]:
        """Extract emotion keywords from content."""
        found: list[str] = []
        for keyword in _EMOTION_KEYWORDS:
            if keyword in content:
                found.append(keyword)
        return found

    def _extract_operation(self, content: str, intent: str) -> str:
        """Extract operation type from content.

        Returns one of: search/analyze/compare/write/ask, or "" if none.
        """
        for op_type, patterns in _OPERATION_PATTERNS.items():
            for pattern in patterns:
                if pattern.search(content):
                    return op_type

        # Infer from intent if no explicit operation found
        intent_to_op = {
            "retrospective_query": "search",
            "advice_seeking": "ask",
            "entity_query": "search",
        }
        return intent_to_op.get(intent, "")

    def _detect_multi_task(self, content: str) -> tuple[bool, list[str]]:
        """Detect if the message contains multiple tasks.

        Returns (is_multi_task, sub_task_descriptions).
        """
        # Check for multi-task connectors
        for connector in _MULTI_TASK_CONNECTORS:
            if connector in content:
                # Split on the connector
                parts = re.split(rf"{connector}", content)
                parts = [p.strip() for p in parts if p.strip()]
                if len(parts) >= 2:
                    return True, parts

        return False, []

    def _extract_style_constraints(self, content: str) -> list[str]:
        """Extract user-expressed style constraints.

        Returns list of constraint labels: short/detailed/gentle/direct/formal/casual.
        """
        constraints: list[str] = []
        for pattern, label in _STYLE_CONSTRAINTS:
            if pattern.search(content):
                constraints.append(label)
        return constraints


__all__ = ["SlotExtractor", "SlotResult"]
