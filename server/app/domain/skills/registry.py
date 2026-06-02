"""SkillRegistry — register and greedily select skills for one diary analysis."""

from __future__ import annotations

import logging
import time

from app.domain.skills.base import ACTIVATION_THRESHOLD, BaseSkill
from app.domain.skills.types import SkillProfileContext
from app.shared.tracing import (
    NoOpSkillActivationTracer,
    SkillActivationRecord,
    SkillActivationTracer,
)

logger = logging.getLogger(__name__)


class SkillRegistry:
    """Manage skills and select activated ones under a token budget."""

    def __init__(self, tracer: SkillActivationTracer | None = None) -> None:
        self._skills: dict[str, BaseSkill] = {}
        self._tracer = tracer or NoOpSkillActivationTracer()

    @property
    def skills(self) -> dict[str, BaseSkill]:
        return dict(self._skills)

    def register(self, skill: BaseSkill) -> None:
        name = skill.metadata.name
        if name in self._skills:
            logger.warning("Skill '%s' already registered; overwriting", name)
        self._skills[name] = skill
        logger.info(
            "Registered skill name=%s category=%s priority=%.2f token_cost=%d",
            name,
            skill.metadata.category,
            skill.metadata.priority,
            skill.metadata.token_cost_estimate,
        )

    def get_skill(self, name: str) -> BaseSkill | None:
        return self._skills.get(name)

    def unregister(self, name: str) -> bool:
        if name not in self._skills:
            return False
        del self._skills[name]
        logger.info("Unregistered skill name=%s", name)
        return True

    def select_skills(
        self,
        text: str,
        profile: SkillProfileContext | None = None,
        *,
        token_budget: int = 4000,
    ) -> list[BaseSkill]:
        """Greedy selection by activation_score * priority within token budget."""
        if not self._skills or token_budget <= 0:
            return []

        candidates: list[tuple[float, BaseSkill]] = []
        digest = text[:200]

        for skill in self._skills.values():
            started = time.perf_counter()
            try:
                score = skill.activation_score(text, profile)
                activated = score >= ACTIVATION_THRESHOLD
                reason = self._activation_reason(skill, score, activated, profile)
            except Exception as exc:
                latency_ms = (time.perf_counter() - started) * 1000
                self._tracer.record(
                    SkillActivationRecord(
                        skill_name=skill.metadata.name,
                        score=0.0,
                        threshold=ACTIVATION_THRESHOLD,
                        activated=False,
                        reason=f"activation_error: {exc}",
                        input_digest=digest,
                        latency_ms=latency_ms,
                    )
                )
                logger.warning(
                    "Skill '%s' activation_score failed: %s",
                    skill.metadata.name,
                    exc,
                )
                continue

            latency_ms = (time.perf_counter() - started) * 1000
            self._tracer.record(
                SkillActivationRecord(
                    skill_name=skill.metadata.name,
                    score=score,
                    threshold=ACTIVATION_THRESHOLD,
                    activated=activated,
                    reason=reason,
                    input_digest=digest,
                    latency_ms=latency_ms,
                )
            )

            if not activated:
                logger.debug(
                    "Skill '%s' suppressed score=%.2f threshold=%.2f",
                    skill.metadata.name,
                    score,
                    ACTIVATION_THRESHOLD,
                )
                continue

            sort_score = score * skill.metadata.priority
            candidates.append((sort_score, skill))

        candidates.sort(key=lambda item: item[0], reverse=True)

        selected: list[BaseSkill] = []
        remaining = token_budget
        total_cost = 0

        for sort_score, skill in candidates:
            cost = skill.metadata.token_cost_estimate
            if cost <= remaining:
                selected.append(skill)
                remaining -= cost
                total_cost += cost
                logger.info(
                    "Activated skill name=%s score=%.3f token_cost=%d remaining=%d",
                    skill.metadata.name,
                    sort_score,
                    cost,
                    remaining,
                )
            else:
                logger.info(
                    "Skipped skill name=%s token_cost=%d remaining=%d",
                    skill.metadata.name,
                    cost,
                    remaining,
                )

        logger.info(
            "Skill selection complete activated=%d/%d token_cost=%d/%d",
            len(selected),
            len(self._skills),
            total_cost,
            token_budget,
        )
        return selected

    @staticmethod
    def _activation_reason(
        skill: BaseSkill,
        score: float,
        activated: bool,
        profile: SkillProfileContext | None,
    ) -> str:
        intent = (profile or {}).get("intent", "pure_record")
        status = "activated" if activated else "suppressed"
        return (
            f"{status}; score={score:.2f}; threshold={ACTIVATION_THRESHOLD}; "
            f"intent={intent}; skill={skill.metadata.name}"
        )


def create_default_registry(
    tracer: SkillActivationTracer | None = None,
) -> SkillRegistry:
    """Register all MVP and stub skills for standalone testing."""
    from app.domain.skills.crisis_detector import CrisisDetectorSkill
    from app.domain.skills.sentiment_skill import SentimentSkill
    from app.domain.skills.stubs import (
        AddressSkill,
        HabitTrackerSkill,
        MemoryReaderSkill,
        MemoryWriterSkill,
        PatternDetectorSkill,
        SearchDiarySkill,
        SummaryGeneratorSkill,
        WeatherSkill,
    )

    registry = SkillRegistry(tracer=tracer)
    for skill in (
        CrisisDetectorSkill(),
        SentimentSkill(),
        PatternDetectorSkill(),
        HabitTrackerSkill(),
        MemoryReaderSkill(),
        MemoryWriterSkill(),
        SummaryGeneratorSkill(),
        SearchDiarySkill(),
        WeatherSkill(),
        AddressSkill(),
    ):
        registry.register(skill)
    return registry
