"""Skill system — registry, MVP skills, and stubs."""

from app.domain.skills.base import ACTIVATION_THRESHOLD, BaseSkill
from app.domain.skills.crisis_detector import CrisisDetectorSkill, estimate_emotion_from_content
from app.domain.skills.registry import SkillRegistry, create_default_registry
from app.domain.skills.sentiment_skill import SentimentSkill
from app.domain.skills.stubs import (
    AddressSkill,
    HabitTrackerSkill,
    MemoryReaderSkill,
    MemoryWriterSkill,
    PatternDetectorSkill,
    SearchDiarySkill,
    StubSkill,
    SummaryGeneratorSkill,
    WeatherSkill,
)
from app.domain.skills.types import (
    SkillCategory,
    SkillExecutionContext,
    SkillMetadata,
    SkillProfileContext,
)

__all__ = [
    "ACTIVATION_THRESHOLD",
    "AddressSkill",
    "BaseSkill",
    "CrisisDetectorSkill",
    "HabitTrackerSkill",
    "MemoryReaderSkill",
    "MemoryWriterSkill",
    "PatternDetectorSkill",
    "SearchDiarySkill",
    "SentimentSkill",
    "SkillCategory",
    "SkillExecutionContext",
    "SkillMetadata",
    "SkillProfileContext",
    "SkillRegistry",
    "StubSkill",
    "SummaryGeneratorSkill",
    "WeatherSkill",
    "create_default_registry",
    "estimate_emotion_from_content",
]
