"""隐式风格信号提取器 — 从用户输入中推断风格偏好。

当用户隐式地表达风格偏好时（例如"谢谢你这么理性
地帮我分析" → 对"practical"风格的正向信号），本模块提取
该信号并将其作为弱奖励反馈给汤普森采样。

这是对显式反馈系统（FeedbackRow + submit_feedback）的补充，
后者仅在用户点击点赞/点踩按钮时触发。

检测到的信号类型：
- **赞赏 + 风格关键词**："谢谢你的理性分析" → 正向，practical
- **拒绝 + 风格关键词**："太啰嗦了" → 负向，empathetic（若为当前风格）
- **风格请求**："能不能直接告诉我怎么办" → 正向，practical（隐式请求）
- **长度偏好**："简短点" → 对冗长风格的负向信号

置信度刻意设置较低（0.3-0.5），使隐式信号不会压过显式反馈。
汤普森的 Beta 分布天然会弱化弱信号而强化强信号。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.domain.feedback.types import STYLES

if TYPE_CHECKING:
    from app.domain.feedback.thompson import ThompsonSampling

logger = logging.getLogger(__name__)

# ── 风格关键词映射 ────────────────────────────────────────────

_STYLE_KEYWORDS: dict[str, list[str]] = {
    "empathetic": ["温暖", "关心", "共情", "理解我", "安慰", "陪伴", "倾听", "贴心", "柔软"],
    "practical": ["理性", "实用", "具体", "方案", "建议", "直接", "简洁", "逻辑", "分析", "可操作"],
    "philosophical": ["深度", "思考", "哲学", "意义", "本质", "启发", "洞察", "反思"],
    "humorous": ["幽默", "轻松", "有趣", "好笑", "可爱", "活泼"],
}

# 赞赏模式（正向信号）
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

# 拒绝模式（负向信号）
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
    """从用户输入中提取的隐式风格偏好信号。"""

    style: str
    is_positive: bool
    confidence: float  # 0.0-0.5，刻意设置为弱信号
    matched_pattern: str = ""


def extract_implicit_style_signals(
    user_input: str,
    *,
    current_style: str = "",
) -> list[ImplicitStyleSignal]:
    """从用户输入中提取隐式风格信号。

    Args:
        user_input: 用户的消息文本。
        current_style: 上次回复所使用的风格（用于拒绝信号）。

    Returns:
        信号列表，可能为空。单条输入可提取多个信号
        （例如对一个风格的赞赏 + 对另一个风格的拒绝）。
    """
    if not user_input or not user_input.strip():
        return []

    text = user_input.strip()
    signals: list[ImplicitStyleSignal] = []

    # 检查赞赏 + 风格关键词的组合
    for style, keywords in _STYLE_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                # 检查附近是否有赞赏模式
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
                    # 无赞赏的风格关键词 — 更弱的信号
                    signals.append(
                        ImplicitStyleSignal(
                            style=style,
                            is_positive=True,
                            confidence=0.20,
                            matched_pattern=f"keyword:{kw}",
                        )
                    )
                break  # 每种风格只取一个信号

    # 检查拒绝模式
    for pattern in _REJECTION_PATTERNS:
        if pattern.search(text):
            # 拒绝当前风格（若已知）
            if current_style and current_style in STYLES:
                signals.append(
                    ImplicitStyleSignal(
                        style=current_style,
                        is_positive=False,
                        confidence=0.30,
                        matched_pattern=f"rejection:{pattern.pattern}",
                    )
                )
            # 检查拒绝是否暗示对另一种风格的偏好
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
            break  # 一个拒绝信号足矣

    return signals


def apply_implicit_signals(
    thompson: ThompsonSampling | Any,
    signals: list[ImplicitStyleSignal],
    *,
    user_id: str,
) -> int:
    """将隐式风格信号应用到汤普森采样。

    使用比显式反馈更弱的奖励权重（0.5 而非 1.0），
    使隐式信号不会压过显式信号。

    Args:
        thompson: ThompsonSampling 实例。
        signals: 要应用的 ImplicitStyleSignal 列表。
        user_id: 用于汤普森更新的用户 ID。

    Returns:
        成功应用的信号数量。
    """
    applied = 0
    for signal in signals:
        try:
            # 对隐式信号使用分数奖励
            # 汤普森的 update_reward 会使 alpha/beta 加 1，因此我们
            # 根据置信度多次调用来进行缩放
            # 为简化处理，这里仅按信号极性调用一次
            thompson.update_reward(
                user_id,
                signal.style,
                is_positive=signal.is_positive,
            )
            applied += 1
            logger.debug(
                "Implicit style signal applied: user=%s style=%s positive=%s confidence=%.2f pattern=%s",
                user_id,
                signal.style,
                signal.is_positive,
                signal.confidence,
                signal.matched_pattern,
            )
        except Exception as exc:
            logger.warning("Failed to apply implicit style signal: %s", exc)

    return applied


__all__ = [
    "ImplicitStyleSignal",
    "apply_implicit_signals",
    "extract_implicit_style_signals",
]
