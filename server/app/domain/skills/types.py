"""技能系统的领域类型。"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, TypedDict

from pydantic import BaseModel, Field


class SkillCategory(StrEnum):
    RETRIEVAL = "retrieval"
    ANALYSIS = "analysis"
    GENERATION = "generation"
    EXTERNAL = "external"
    MEMORY = "memory"


class SkillMetadata(BaseModel):
    """SkillRegistry 用于选择和预算评估的元数据。"""

    name: str
    description: str
    triggers: list[str] = Field(default_factory=list)
    priority: float = Field(default=1.0, ge=0.0)
    category: SkillCategory = SkillCategory.ANALYSIS
    token_cost_estimate: int = Field(default=100, ge=0)
    requires_db: bool = False
    requires_network: bool = False


class SkillProfileContext(TypedDict, total=False):
    """传入技能激活的可选画像/意图上下文。"""

    intent: str
    user_id: str
    recurring_topics: list[str]


class SkillExecutionContext(TypedDict, total=False):
    """技能执行的运行时上下文。"""

    diary_content: str
    user_id: str
    intent: str
    llm: Any
