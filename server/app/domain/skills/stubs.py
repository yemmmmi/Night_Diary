"""Stub skills reserved for post-MVP activation mini-PRs."""

from __future__ import annotations

from typing import Any

from app.domain.skills.base import BaseSkill
from app.domain.skills.types import SkillCategory, SkillMetadata, SkillProfileContext


class StubSkill(BaseSkill):
    """Inactive placeholder skill — registered but never activated in MVP."""

    def activation_score(
        self,
        text: str,
        profile: SkillProfileContext | None = None,
    ) -> float:
        _ = (text, profile)
        return 0.0

    def can_activate(
        self,
        text: str,
        profile: SkillProfileContext | None = None,
    ) -> bool:
        _ = (text, profile)
        return False

    def execute(self, context: dict[str, Any], **kwargs: Any) -> str:
        _ = (context, kwargs)
        raise NotImplementedError(f"{self.metadata.name} is stubbed in Phase B-6 MVP")


class PatternDetectorSkill(StubSkill):
    metadata = SkillMetadata(
        name="pattern_detector",
        description="识别跨日记的行为/情绪模式",
        triggers=["模式", "趋势", "总是"],
        priority=1.1,
        category=SkillCategory.ANALYSIS,
        token_cost_estimate=120,
        requires_db=True,
    )


class HabitTrackerSkill(StubSkill):
    metadata = SkillMetadata(
        name="habit_tracker",
        description="追踪用户习惯与目标进度",
        triggers=["习惯", "坚持", "打卡"],
        priority=1.0,
        category=SkillCategory.ANALYSIS,
        token_cost_estimate=100,
        requires_db=True,
    )


class MemoryReaderSkill(StubSkill):
    metadata = SkillMetadata(
        name="memory_reader",
        description="读取情景/长期记忆上下文",
        triggers=["回忆", "之前", "上次"],
        priority=1.3,
        category=SkillCategory.MEMORY,
        token_cost_estimate=80,
        requires_db=True,
    )


class MemoryWriterSkill(StubSkill):
    metadata = SkillMetadata(
        name="memory_writer",
        description="写入新的情景记忆条目",
        triggers=["记住", "下次", "提醒"],
        priority=1.0,
        category=SkillCategory.MEMORY,
        token_cost_estimate=80,
        requires_db=True,
    )


class SummaryGeneratorSkill(StubSkill):
    metadata = SkillMetadata(
        name="summary_generator",
        description="生成日记或阶段总结",
        triggers=["总结", "回顾", "汇总"],
        priority=0.9,
        category=SkillCategory.GENERATION,
        token_cost_estimate=180,
    )


class SearchDiarySkill(StubSkill):
    metadata = SkillMetadata(
        name="search_diary_skill",
        description="检索历史日记片段",
        triggers=["搜索", "查找", "以前写过"],
        priority=1.1,
        category=SkillCategory.RETRIEVAL,
        token_cost_estimate=140,
        requires_db=True,
    )


class WeatherSkill(StubSkill):
    metadata = SkillMetadata(
        name="weather_skill",
        description="补充天气上下文",
        triggers=["天气", "下雨", "晴天"],
        priority=0.8,
        category=SkillCategory.EXTERNAL,
        token_cost_estimate=60,
        requires_network=True,
    )


class AddressSkill(StubSkill):
    metadata = SkillMetadata(
        name="address_skill",
        description="解析地点/地址上下文",
        triggers=["在", "去了", "地点"],
        priority=0.7,
        category=SkillCategory.EXTERNAL,
        token_cost_estimate=50,
    )
