"""EntityTrackerSkill — scene 2 skill that queries the entity graph.

Activates when the user asks about a specific person or entity's status.
"""

from __future__ import annotations

import logging
from typing import Any

from app.domain.skills.base import BaseSkill
from app.domain.skills.types import SkillCategory, SkillMetadata, SkillProfileContext

logger = logging.getLogger(__name__)

_PERSON_REFERENCES = (
    "妈妈", "爸爸", "老公", "老婆", "男友", "女友",
    "儿子", "女儿", "老板", "同事", "老师", "朋友",
)


class EntityTrackerSkill(BaseSkill):
    """Query the entity graph when the user mentions specific people/entities."""

    metadata = SkillMetadata(
        name="entity_tracker",
        description="查询实体图中人物/实体的关系和情感关联",
        triggers=list(_PERSON_REFERENCES) + ["怎么样", "怎么了", "最近"],
        priority=1.3,
        category=SkillCategory.MEMORY,
        token_cost_estimate=100,
        requires_db=True,
    )

    def activation_score(
        self,
        text: str,
        profile: SkillProfileContext | None = None,
    ) -> float:
        intent = (profile or {}).get("intent", "casual_chat")
        if intent == "entity_query":
            return 0.9
        hits = sum(1 for kw in _PERSON_REFERENCES if kw in text)
        if hits >= 1 and any(kw in text for kw in ("怎么样", "怎么了", "最近")):
            return 0.8
        if hits >= 1:
            return 0.5
        return 0.1

    def execute(self, context: dict[str, Any], **kwargs: Any) -> str:
        return "[entity_tracker] 已触发实体图查询，请在上下文中包含相关实体信息。"
