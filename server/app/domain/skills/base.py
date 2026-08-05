"""BaseSkill 抽象类，用于可插拔的日记分析技能。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.domain.skills.types import SkillMetadata, SkillProfileContext

ACTIVATION_THRESHOLD = 0.3


class BaseSkill(ABC):
    """技能契约：计算激活分数、阈值门控、执行逻辑。"""

    metadata: SkillMetadata

    @abstractmethod
    def activation_score(
        self,
        text: str,
        profile: SkillProfileContext | None = None,
    ) -> float:
        """返回 [0.0, 1.0] 范围内的激活概率。"""

    def can_activate(
        self,
        text: str,
        profile: SkillProfileContext | None = None,
    ) -> bool:
        """判断该技能是否达到全局激活阈值。"""
        return self.activation_score(text, profile) >= ACTIVATION_THRESHOLD

    @abstractmethod
    def execute(self, context: dict[str, Any], **kwargs: Any) -> str:
        """执行技能并返回文本结果，供下游智能体使用。"""
