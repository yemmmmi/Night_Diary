"""CrisisDetectorSkill — 检测极端负面情绪并安全升级处理。"""

from __future__ import annotations

import logging
from typing import Any

from app.domain.skills.base import BaseSkill
from app.domain.skills.types import SkillCategory, SkillMetadata, SkillProfileContext
from app.shared.emotion_estimator import EmotionEstimator, get_emotion_estimator

logger = logging.getLogger(__name__)

CRISIS_RESOURCES = (
    "如果你正在经历极度痛苦，请记住你并不孤单。"
    "以下资源可以提供帮助：\n"
    "• 全国心理援助热线：400-161-9995\n"
    "• 北京心理危机研究与干预中心：010-82951332\n"
    "• 生命热线：400-821-1215\n"
    "请不要独自承受，寻求专业帮助是勇敢的选择。"
)


class CrisisDetectorSkill(BaseSkill):
    """检测危机级别的负面情绪并返回支持性资源。

    情绪评分委托给共享的 :class:`EmotionEstimator`（关键词启发式判断的唯一
    数据源），而非在技能内部保留词库副本。
    """

    metadata = SkillMetadata(
        name="crisis_detector",
        description="识别极端负面情绪并触发安全干预",
        triggers=["想死", "不想活", "自杀", "emotional_support"],
        priority=2.0,
        category=SkillCategory.ANALYSIS,
        token_cost_estimate=50,
    )

    def __init__(self, emotion_estimator: EmotionEstimator | None = None) -> None:
        self._emotion = emotion_estimator or get_emotion_estimator()

    def activation_score(
        self,
        text: str,
        profile: SkillProfileContext | None = None,
    ) -> float:
        intent = (profile or {}).get("intent", "pure_record")

        if self._emotion.has_severe_signal(text):
            return 1.0
        if intent == "emotional_support":
            return 0.8

        negative_count = self._emotion.count_negative_signals(text)
        if negative_count >= 3:
            return 0.7
        if negative_count >= 1:
            return 0.4
        return 0.2

    def execute(self, context: dict[str, Any], **kwargs: Any) -> str:
        diary_content = context.get("diary_content", "")
        user_id = context.get("user_id", "default")

        if not diary_content:
            return "未检测到危机信号。"

        estimate = self._emotion.estimate(diary_content)
        if estimate.score < self._emotion.crisis_threshold:
            logger.warning(
                "Crisis detected score=%.2f threshold=%.2f user_id=%s",
                estimate.score,
                self._emotion.crisis_threshold,
                user_id,
            )
            parts = [f"⚠️ 危机情绪检测触发（情绪分数: {estimate.score:.2f}）"]
            if estimate.matched_severe:
                parts.append(f"检测到严重负面信号关键词: {', '.join(estimate.matched_severe)}")
            parts.extend(["", "【升级响应协议已触发】", CRISIS_RESOURCES])
            return "\n".join(parts)

        return f"情绪状态正常（情绪分数: {estimate.score:.2f}），未检测到危机信号。"
