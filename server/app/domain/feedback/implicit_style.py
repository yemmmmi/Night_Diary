"""Implicit style signal extractor — infers style preferences from user input.

When the user expresses a style preference implicitly (e.g., "谢谢你这么理性
地帮我分析" → positive signal for "practical" style), this module extracts
the signal for downstream consumption.

This complements the explicit feedback system (FeedbackRow + submit_feedback)
which only fires when the user clicks a thumbs-up/down button.

Signal types detected:
- **Appreciation + style keyword**: "谢谢你的理性分析" → positive, practical
- **Rejection + style keyword**: "太啰嗦了" → negative, empathetic (if current style)
- **Style request**: "能不能直接告诉我怎么办" → positive, practical (implicit request)
- **Length preference**: "简短点" → negative for verbose styles

Confidence is intentionally low (0.3-0.5) so implicit signals don't
overpower explicit feedback.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.domain.feedback.types import STYLES

logger = logging.getLogger(__name__)

# ── Style keyword mapping ────────────────────────────────────────────

_STYLE_KEYWORDS: dict[str, list[str]] = {
    "empathetic": ["温暖", "关心", "共情", "理解我", "安慰", "陪伴", "倾听", "贴心", "柔软"],
    "practical": ["理性", "实用", "具体", "方案", "建议", "直接", "简洁", "逻辑", "分析", "可操作"],
    "philosophical": ["深度", "思考", "哲学", "意义", "本质", "启发", "洞察", "反思"],
    "humorous": ["幽默", "轻松", "有趣", "好笑", "可爱", "活泼"],
}

# Appreciation patterns (positive signal)
_APPRECIATION_PATTERNS = [
    re.compile(r"谢谢.{0,10}"),
    re.compile(r"感谢.{0,10}"),
    re.compile(r"很好.{0,5}"),
    re.compile(r"不错.{0,5}"),
    re.compile(r"有帮助"),
    re.compile(r"说(得|的)对"),
    re.compile(r"正是.{0,5}需要"),
    re.compile(r"说到.{0,5}心(里|坎)"),
]

# Rejection patterns (negative signal)
_REJECTION_PATTERNS = [
    re.compile(r"太(啰嗦|长|多)"),
    re.compile(r"不要.{0,5}(这样|那种)"),
    re.compile(r"不需要.{0,5}(安慰|道理)"),
    re.compile(r"能不能.{0,5}(直接|简单|具体)"),
    re.compile(r"想(要|要的)是.{0,10}"),
    re.compile(r"没什么帮助"),
    re.compile(r"不太(好|行)"),
]


@dataclass
class ImplicitStyleSignal:
    """An implicit style preference signal extracted from user input."""

    style: str
    is_positive: bool
    confidence: float  # 0.0-0.5, intentionally weak
    matched_pattern: str = ""


def extract_implicit_style_signals(
    user_input: str,
    *,
    current_style: str = "",
) -> list[ImplicitStyleSignal]:
    """Extract implicit style signals from user input.

    Args:
        user_input: The user's message text.
        current_style: The style used in the last reply (for rejection signals).

    Returns:
        List of signals, possibly empty. Multiple signals can be extracted
        from a single input (e.g., appreciation for one style + rejection
        of another).
    """
    if not user_input or not user_input.strip():
        return []

    text = user_input.strip()
    signals: list[ImplicitStyleSignal] = []

    # Check appreciation + style keyword combinations
    for style, keywords in _STYLE_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                # Check if there's an appreciation pattern nearby
                for pattern in _APPRECIATION_PATTERNS:
                    if pattern.search(text):
                        signals.append(
                            ImplicitStyleSignal(
                                style=style,
                                is_positive=True,
                                confidence=0.35,
                                matched_pattern=f"appreciation+{kw}",
                            )
                        )
                        break
                else:
                    # Style keyword without appreciation — weaker signal
                    signals.append(
                        ImplicitStyleSignal(
                            style=style,
                            is_positive=True,
                            confidence=0.20,
                            matched_pattern=f"keyword:{kw}",
                        )
                    )
                break  # Only one signal per style

    # Check rejection patterns
    for pattern in _REJECTION_PATTERNS:
        if pattern.search(text):
            # Rejection of current style (if known)
            if current_style and current_style in STYLES:
                signals.append(
                    ImplicitStyleSignal(
                        style=current_style,
                        is_positive=False,
                        confidence=0.30,
                        matched_pattern=f"rejection:{pattern.pattern}",
                    )
                )
            # Check if rejection implies preference for another style
            if "直接" in text or "简单" in text or "具体" in text:
                signals.append(
                    ImplicitStyleSignal(
                        style="practical",
                        is_positive=True,
                        confidence=0.25,
                        matched_pattern="rejection→practical",
                    )
                )
            elif "不需要" in text and "道理" in text:
                signals.append(
                    ImplicitStyleSignal(
                        style="philosophical",
                        is_positive=False,
                        confidence=0.25,
                        matched_pattern="rejection→not_philosophical",
                    )
                )
            break  # One rejection signal is enough

    return signals


__all__ = [
    "ImplicitStyleSignal",
    "extract_implicit_style_signals",
]
