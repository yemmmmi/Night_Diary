"""Skill system — registry, MVP skills, and extensible framework.

To add a new skill:
1. Subclass ``BaseSkill`` (implement ``activation_score``, ``can_activate``, ``execute``)
2. Register it in ``create_default_registry()``
"""

from app.domain.skills.base import ACTIVATION_THRESHOLD, BaseSkill
from app.domain.skills.crisis_detector import CrisisDetectorSkill
from app.domain.skills.registry import SkillRegistry, create_default_registry
from app.domain.skills.sentiment_skill import SentimentSkill
from app.domain.skills.types import (
    SkillCategory,
    SkillExecutionContext,
    SkillMetadata,
    SkillProfileContext,
)

__all__ = [
    "ACTIVATION_THRESHOLD",
    "BaseSkill",
    "CrisisDetectorSkill",
    "SentimentSkill",
    "SkillCategory",
    "SkillExecutionContext",
    "SkillMetadata",
    "SkillProfileContext",
    "SkillRegistry",
    "create_default_registry",
]
