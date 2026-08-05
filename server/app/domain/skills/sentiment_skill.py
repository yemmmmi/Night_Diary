"""SentimentSkill — 检测日记文本中的情感极性与强度。"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from app.domain.skills.base import BaseSkill
from app.domain.skills.types import SkillCategory, SkillMetadata, SkillProfileContext

logger = logging.getLogger(__name__)

_EMOTION_KEYWORDS = (
    "开心",
    "难过",
    "焦虑",
    "生气",
    "愤怒",
    "伤心",
    "高兴",
    "烦躁",
    "压力",
    "崩溃",
    "抑郁",
    "孤独",
    "幸福",
    "感动",
    "失望",
    "无聊",
    "兴奋",
    "紧张",
    "害怕",
    "恐惧",
    "羞愧",
    "内疚",
    "嫉妒",
    "委屈",
    "绝望",
    "迷茫",
    "疲惫",
    "心累",
    "释然",
    "满足",
    "感恩",
)


class LLMClient(Protocol):
    def invoke(self, prompt: str) -> Any: ...


class SentimentSkill(BaseSkill):
    """当存在情感线索时分析情感极性与强度。"""

    metadata = SkillMetadata(
        name="sentiment_skill",
        description="分析文本情感倾向、强度和关键情感词",
        triggers=["emotional_support", "难过", "焦虑", "开心"],
        priority=1.2,
        category=SkillCategory.ANALYSIS,
        token_cost_estimate=150,
        requires_network=True,
    )

    def activation_score(
        self,
        text: str,
        profile: SkillProfileContext | None = None,
    ) -> float:
        intent = (profile or {}).get("intent", "pure_record")

        if intent == "emotional_support":
            return 0.9

        emotion_count = sum(1 for keyword in _EMOTION_KEYWORDS if keyword in text)
        if emotion_count >= 2:
            return 0.85
        if emotion_count == 1:
            return 0.7
        if intent == "retrospective_review":
            return 0.6
        if intent == "pure_record" and len(text) > 80:
            return 0.4
        return 0.15

    def execute(self, context: dict[str, Any], **kwargs: Any) -> str:
        text = kwargs.get("text") or context.get("diary_content", "")
        if not text.strip():
            return "无法分析空内容"

        llm = context.get("llm")
        if llm is None:
            return "情感分析暂时不可用：缺少 LLM 实例"

        prompt = (
            "请对以下文本进行情感分析，严格按照以下格式输出：\n"
            "情感倾向：[正面/负面/中性]\n"
            "情感强度：[1-5]（1=很弱，5=很强）\n"
            "关键情感词：[词1, 词2, ...]（最多5个）\n\n"
            f"文本：{text}"
        )
        try:
            response = llm.invoke(prompt)
            content = getattr(response, "content", response)
            return str(content)
        except Exception as exc:
            logger.error("SentimentSkill failed: %s", exc)
            return "情感分析暂时不可用"
