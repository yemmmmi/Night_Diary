"""Domain types for the Skill system."""

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
    """Metadata used by SkillRegistry for selection and budgeting."""

    name: str
    description: str
    triggers: list[str] = Field(default_factory=list)
    priority: float = Field(default=1.0, ge=0.0)
    category: SkillCategory = SkillCategory.ANALYSIS
    token_cost_estimate: int = Field(default=100, ge=0)
    requires_db: bool = False
    requires_network: bool = False


class SkillProfileContext(TypedDict, total=False):
    """Optional profile/intent context passed into skill activation."""

    intent: str
    user_id: str
    recurring_topics: list[str]


class SkillExecutionContext(TypedDict, total=False):
    """Runtime context for skill execution."""

    diary_content: str
    user_id: str
    intent: str
    llm: Any
