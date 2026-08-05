"""MemoryRecallSkill — 场景 2 技能，检索相关的情节记忆。

当用户提及过去的事件或询问对话历史时激活。
该技能为场景 2 专用（多轮对话），补充场景 1 的技能
（crisis_detector、sentiment_skill）。
"""

from __future__ import annotations

import logging
from typing import Any

from app.domain.skills.base import BaseSkill
from app.domain.skills.types import SkillCategory, SkillMetadata, SkillProfileContext

logger = logging.getLogger(__name__)

_RECALL_TRIGGERS = (
    "上次",
    "之前",
    "记得吗",
    "说过",
    "聊过",
    "提到过",
    "那天",
    "那次",
    "以前",
    "昨天",
    "上周",
)


class MemoryRecallSkill(BaseSkill):
    """当用户提及过去时，检索相关的情节记忆。"""

    metadata = SkillMetadata(
        name="memory_recall",
        description="回溯用户提及的过往事件，检索相关情节记忆",
        triggers=list(_RECALL_TRIGGERS),
        priority=1.5,
        category=SkillCategory.RETRIEVAL,
        token_cost_estimate=200,
        requires_db=True,
    )

    def activation_score(
        self,
        text: str,
        profile: SkillProfileContext | None = None,
    ) -> float:
        intent = (profile or {}).get("intent", "casual_chat")
        if intent in ("retrospective_query", "advice_seeking"):
            return 0.85
        hits = sum(1 for kw in _RECALL_TRIGGERS if kw in text)
        if hits >= 2:
            return 0.8
        if hits == 1:
            return 0.6
        return 0.1

    def execute(self, context: dict[str, Any], **kwargs: Any) -> str:
        """返回需要记忆回溯的提示（实际检索由上游完成）。"""
        return "[memory_recall] 已触发记忆回溯，请在上下文中包含相关情节记忆。"
