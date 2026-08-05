"""脏记忆预防 —— 针对情景记忆写入的四维门控。

防止低质量或有害的记忆进入情景存储。每次写入都要经过四道门控：

1. **情感显著性**：跳过情感信号接近零的条目
   （像"今天吃了饭"这类平淡记录不配占用记忆槽位）。
2. **内容有效性**：拒绝空、纯空白或荒谬地过短的输入，
   它们会产生无意义的事件摘要。
3. **危机污染**：不持久化原始危机内容 —— 危机响应是安全攸关的，
   不应在未来上下文中作为"记忆"被重放。危机信号由 CrisisGuard 单独处理。
4. **去重**：拒绝与 deque 中已有条目近乎重复的写入
   （时间窗口内 event_summary 相同）。

门控设计为低成本（无 LLM 调用）且快速（O(1) 或小 n 的 O(n)）。
它在 MemoryGateway.persist_episodic 之前运行。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.domain.memory.types import EpisodicEntry

logger = logging.getLogger(__name__)

# ── 门控阈值 ──────────────────────────────────────────────────

_MIN_EVENT_SUMMARY_LEN = 3
_MIN_EMOTIONAL_SIGNAL = 0.15  # abs(mood_score - 0.5) 必须超过此值
_DEDUP_WINDOW_HOURS = 24
_DEDUP_SIMILARITY_THRESHOLD = 0.85  # 用于去重的 char Jaccard 阈值

# 不应被持久化为情景记忆的危机关键词
_CRISIS_KEYWORDS = frozenset(
    {
        "不想活",
        "自杀",
        "结束生命",
        "活不下去",
        "想死",
        "杀了",
        "伤害自己",
        "了结",
        "跳楼",
        "吃药结束",
    }
)


@dataclass
class GateResult:
    """四维记忆门控的结果。"""

    passed: bool
    reason: str = ""
    gate_name: str = ""


def _char_jaccard(a: str, b: str) -> float:
    """字符级 Jaccard 相似度（对短中文文本处理良好）。"""
    if not a or not b:
        return 0.0
    set_a = set(a)
    set_b = set(b)
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


def check_memory_gate(
    event_summary: str,
    emotion: str,
    mood_score: float,
    importance: float,
    content: str = "",
    existing_entries: list[EpisodicEntry] | None = None,
) -> GateResult:
    """对一次提议的情景记忆写入运行四维门控。

    Args:
        event_summary: 提议的事件摘要。
        emotion: 情绪标签。
        mood_score: 情绪分数（0.0-1.0）。
        importance: 重要性分数（0.0-1.0）。
        content: 原始内容（用于危机检测）。
        existing_entries: 用于去重检查的近期条目。

    Returns:
        GateResult，指示该写入是否应继续进行。
    """
    # ── 门控 1：内容有效性 ──
    if not event_summary or len(event_summary.strip()) < _MIN_EVENT_SUMMARY_LEN:
        return GateResult(
            passed=False,
            reason=f"Event summary too short (<{_MIN_EVENT_SUMMARY_LEN} chars)",
            gate_name="content_validity",
        )

    # ── 门控 2：危机污染 ──
    check_text = (content or event_summary).lower()
    for keyword in _CRISIS_KEYWORDS:
        if keyword in check_text:
            return GateResult(
                passed=False,
                reason=f"Crisis keyword detected: {keyword}",
                gate_name="crisis_contamination",
            )

    # ── 门控 3：情感显著性 ──
    emotional_signal = abs(mood_score - 0.5)
    if emotional_signal < _MIN_EMOTIONAL_SIGNAL and importance < 0.4:
        return GateResult(
            passed=False,
            reason=f"Low emotional signal ({emotional_signal:.3f} < {_MIN_EMOTIONAL_SIGNAL}) and low importance ({importance:.2f} < 0.4)",
            gate_name="emotional_significance",
        )

    # ── 门控 4：去重 ──
    if existing_entries:
        now = datetime.now(UTC).timestamp()
        window_start = now - timedelta(hours=_DEDUP_WINDOW_HOURS).total_seconds()
        for entry in existing_entries:
            if entry.timestamp < window_start:
                continue
            similarity = _char_jaccard(event_summary, entry.event_summary)
            if similarity >= _DEDUP_SIMILARITY_THRESHOLD:
                return GateResult(
                    passed=False,
                    reason=f"Near-duplicate of existing entry (similarity={similarity:.2f})",
                    gate_name="deduplication",
                )

    return GateResult(passed=True)


def should_persist(
    event_summary: str,
    emotion: str,
    mood_score: float = 0.5,
    importance: float = 0.5,
    content: str = "",
    existing_entries: list[EpisodicEntry] | None = None,
) -> bool:
    """便捷封装：当门控通过时返回 True。

    以 debug 级别记录拒绝原因。
    """
    result = check_memory_gate(
        event_summary=event_summary,
        emotion=emotion,
        mood_score=mood_score,
        importance=importance,
        content=content,
        existing_entries=existing_entries,
    )
    if not result.passed:
        logger.debug(
            "Memory gate rejected: gate=%s reason=%s summary=%s",
            result.gate_name,
            result.reason,
            event_summary[:50],
        )
    return result.passed


__all__ = [
    "GateResult",
    "check_memory_gate",
    "should_persist",
]
