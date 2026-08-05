"""BaseSkill abstract class for pluggable diary analysis skills."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.domain.skills.types import SkillMetadata, SkillProfileContext

ACTIVATION_THRESHOLD = 0.3


class BaseSkill(ABC):
    """Skill contract: score activation, gate with threshold, execute logic."""

    metadata: SkillMetadata

    @abstractmethod
    def activation_score(
        self,
        text: str,
        profile: SkillProfileContext | None = None,
    ) -> float:
        """Return activation probability in [0.0, 1.0]."""

    def can_activate(
        self,
        text: str,
        profile: SkillProfileContext | None = None,
    ) -> bool:
        """Whether the skill clears the global activation threshold."""
        return self.activation_score(text, profile) >= ACTIVATION_THRESHOLD

    @abstractmethod
    def execute(self, context: dict[str, Any], **kwargs: Any) -> str:
        """Run the skill and return a text result for downstream agents."""
