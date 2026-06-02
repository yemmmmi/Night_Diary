"""CrisisDetectorSkill — detect extreme negative emotion and escalate safely."""

from __future__ import annotations

import logging
from typing import Any

from app.domain.skills.base import BaseSkill
from app.domain.skills.types import SkillCategory, SkillMetadata, SkillProfileContext

logger = logging.getLogger(__name__)

CRISIS_EMOTION_THRESHOLD = -0.7

_SEVERE_NEGATIVE_KEYWORDS = (
    "想死",
    "不想活",
    "自杀",
    "结束生命",
    "活着没意思",
    "我不想活了",
    "绝望",
    "崩溃",
    "撑不下去",
    "没有希望",
    "生不如死",
    "伤害自己",
    "自残",
    "割腕",
    "跳楼",
)

_NEGATIVE_KEYWORDS = (
    "难过",
    "痛苦",
    "焦虑",
    "抑郁",
    "孤独",
    "害怕",
    "愤怒",
    "失望",
    "无助",
    "悲伤",
    "压抑",
    "烦躁",
    "失眠",
    "哭",
    "受不了",
    "太累了",
)

CRISIS_RESOURCES = (
    "如果你正在经历极度痛苦，请记住你并不孤单。"
    "以下资源可以提供帮助：\n"
    "• 全国心理援助热线：400-161-9995\n"
    "• 北京心理危机研究与干预中心：010-82951332\n"
    "• 生命热线：400-821-1215\n"
    "请不要独自承受，寻求专业帮助是勇敢的选择。"
)


def estimate_emotion_from_content(content: str) -> float:
    """Keyword-based emotion score in [-1.0, 1.0]. B-7 will centralize this."""
    if not content:
        return 0.0

    score = 0.0
    for word in _SEVERE_NEGATIVE_KEYWORDS:
        if word in content:
            score -= 0.4

    for word in _NEGATIVE_KEYWORDS:
        if word in content:
            score -= 0.15

    positive_keywords = (
        "开心",
        "快乐",
        "幸福",
        "感恩",
        "满足",
        "期待",
        "兴奋",
        "温暖",
        "感动",
        "自豪",
        "放松",
        "愉快",
    )
    for word in positive_keywords:
        if word in content:
            score += 0.15

    return max(-1.0, min(1.0, score))


class CrisisDetectorSkill(BaseSkill):
    """Detect crisis-level negative emotion and return supportive resources."""

    metadata = SkillMetadata(
        name="crisis_detector",
        description="识别极端负面情绪并触发安全干预",
        triggers=["想死", "不想活", "自杀", "emotional_support"],
        priority=2.0,
        category=SkillCategory.ANALYSIS,
        token_cost_estimate=50,
    )

    def activation_score(
        self,
        text: str,
        profile: SkillProfileContext | None = None,
    ) -> float:
        intent = (profile or {}).get("intent", "pure_record")

        if any(keyword in text for keyword in _SEVERE_NEGATIVE_KEYWORDS):
            return 1.0
        if intent == "emotional_support":
            return 0.8

        negative_count = sum(1 for keyword in _NEGATIVE_KEYWORDS if keyword in text)
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

        emotion_score = estimate_emotion_from_content(diary_content)
        if emotion_score < CRISIS_EMOTION_THRESHOLD:
            logger.warning(
                "Crisis detected score=%.2f threshold=%.2f user_id=%s",
                emotion_score,
                CRISIS_EMOTION_THRESHOLD,
                user_id,
            )
            triggered_severe = [w for w in _SEVERE_NEGATIVE_KEYWORDS if w in diary_content]
            parts = [f"⚠️ 危机情绪检测触发（情绪分数: {emotion_score:.2f}）"]
            if triggered_severe:
                parts.append(f"检测到严重负面信号关键词: {', '.join(triggered_severe)}")
            parts.extend(["", "【升级响应协议已触发】", CRISIS_RESOURCES])
            return "\n".join(parts)

        return f"情绪状态正常（情绪分数: {emotion_score:.2f}），未检测到危机信号。"
