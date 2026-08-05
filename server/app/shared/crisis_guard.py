"""CrisisGuard——两个场景共享的危机检测与安全响应。

从 ``SupervisorAgent._detect_crisis`` 中抽取出来，使得场景 2（多轮对话）
可以使用相同的安全网，而无需依赖 Supervisor。

日记分析管道（场景 1）和对话 AI（场景 2）都在用户输入上调用
:meth:`detect`。当它返回 ``True`` 时，调用方必须短路正常生成，并原样返回
:attr:`safe_response`。
"""

from __future__ import annotations

import logging

from app.domain.skills.crisis_detector import CRISIS_RESOURCES
from app.shared.emotion_estimator import EmotionEstimator, get_emotion_estimator

logger = logging.getLogger(__name__)

#: 检测到危机时返回的预构建响应。
#: 在场景 1 中追加到共情回复之后，在场景 2 中直接返回。
CRISIS_SAFE_RESPONSE = (
    "我能感受到你现在正承受着巨大的痛苦, 我在这里陪着你。\n"
    "你的感受是真实的, 但请不要独自承受这些。\n\n" + CRISIS_RESOURCES
)


class CrisisGuard:
    """共享的危机检测，封装 :class:`EmotionEstimator`。

    评估器是关键词启发式和危机分数阈值的唯一真相来源——不存在词表的第三份副本。
    """

    def __init__(self, emotion_estimator: EmotionEstimator | None = None) -> None:
        self._emotion = emotion_estimator or get_emotion_estimator()

    @property
    def safe_response(self) -> str:
        """返回检测到危机时要发送的安全资源文本。"""
        return CRISIS_SAFE_RESPONSE

    def detect(self, text: str) -> bool:
        """当 *text* 显示出危机级别的信号时返回 ``True``。

        两项检查（任一触发即可）：
        1. ``has_severe_signal``——明确的自伤 / 绝望关键词。
        2. ``score < crisis_threshold``——整体情绪分数低于 -0.7。
        """
        if not text or not text.strip():
            return False
        if self._emotion.has_severe_signal(text):
            logger.warning("CrisisGuard: severe signal detected")
            return True
        if self._emotion.score(text) < self._emotion.crisis_threshold:
            logger.warning("CrisisGuard: emotion score below crisis threshold")
            return True
        return False


_singleton: CrisisGuard | None = None


def get_crisis_guard() -> CrisisGuard:
    """返回进程范围内的 :class:`CrisisGuard` 单例。"""
    global _singleton
    if _singleton is None:
        _singleton = CrisisGuard()
    return _singleton


__all__ = ["CRISIS_SAFE_RESPONSE", "CrisisGuard", "get_crisis_guard"]
