"""MemoryRecallSkill — scene 2 skill that retrieves relevant episodic memories.

Activates when the user references past events or asks about conversation history.
This skill is scene-2 specific (multi-turn conversation), complementing the
scene-1 skills (crisis_detector, sentiment_skill).
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
    """Retrieve relevant episodic memories when the user references the past."""

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
        """Return a hint that memory recall is needed (actual retrieval is upstream)."""
        return "[memory_recall] 已触发记忆回溯，请在上下文中包含相关情节记忆。"
