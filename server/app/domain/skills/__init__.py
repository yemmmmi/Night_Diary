"""技能系统 — 注册表、MVP 技能与可扩展框架。

添加新技能的方式：
1. 继承 ``BaseSkill``（实现 ``activation_score``、``can_activate``、``execute``）
2. 在 ``create_default_registry()`` 中注册
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
