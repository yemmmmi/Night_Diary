"""BaseSkill abstract class for pluggable diary analysis skills."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.domain.skills.types import SkillMetadata, SkillProfileContext

ACTIVATION_THRESHOLD = 0.3


class BaseSkill(ABC):
    """Skill contract: score activation, gate with threshold, execute logic.

    ``activation_score`` is the *rule floor* (stage 1) of the registry's
    two-stage scoring: a pure, LLM-free heuristic that stays testable in
    isolation. Stage 2 (see ``SkillRegistry.select_skills``) may additively
    rescue sub-threshold skills with one light LLM call using ``max`` fusion —
    the LLM can only raise a score, never lower one, so any skill the rules
    activated (e.g. crisis severe signal = 1.0) is final.
    """

    metadata: SkillMetadata

    @abstractmethod
    def activation_score(
        self,
        text: str,
        profile: SkillProfileContext | None = None,
    ) -> float:
        """Return activation probability in [0.0, 1.0] (pure-rule stage 1)."""

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
