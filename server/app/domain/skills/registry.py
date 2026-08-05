"""SkillRegistry — 注册并为单次日记分析贪心选择技能。"""

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
    """管理技能并在 token 预算内选择已激活的技能。"""

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
        decision_id: str = "",
    ) -> list[BaseSkill]:
        """在 token 预算内按 activation_score * priority 贪心选择。

        ``decision_id``（若提供）会标记到每条
        :class:`SkillActivationRecord` 上，使这些记录可关联回所属的
        ``agent_decisions`` 条目（Supervisor 在 B-9 中传入其决策 id）。
        """
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
                        decision_id=decision_id,
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
                    decision_id=decision_id,
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
    """工厂：注册所有 MVP 技能，用于独立测试。

    技能框架（BaseSkill、SkillRegistry、此工厂）是可扩展的 —
    新技能继承 BaseSkill 并在此注册。已移除占位存根；
    仅保留已激活的 MVP 技能。
    """
    from app.domain.skills.crisis_detector import CrisisDetectorSkill
    from app.domain.skills.sentiment_skill import SentimentSkill

    registry = SkillRegistry(tracer=tracer)
    for skill in (
        CrisisDetectorSkill(),
        SentimentSkill(),
    ):
        registry.register(skill)
    return registry


def create_diary_registry(
    tracer: SkillActivationTracer | None = None,
) -> SkillRegistry:
    """工厂：注册场景 1（日记分析）的技能。

    与默认注册表共享 crisis_detector 和 sentiment_skill，另外加入
    memory_recall 用于回溯性日记条目（例如"上周和朋友去了公园"
    会触发对相关过往事件的记忆检索）。
    """
    from app.domain.skills.crisis_detector import CrisisDetectorSkill
    from app.domain.skills.memory_recall_skill import MemoryRecallSkill
    from app.domain.skills.sentiment_skill import SentimentSkill

    registry = SkillRegistry(tracer=tracer)
    for skill in (
        CrisisDetectorSkill(),
        SentimentSkill(),
        MemoryRecallSkill(),
    ):
        registry.register(skill)
    return registry


def create_chat_registry(
    tracer: SkillActivationTracer | None = None,
) -> SkillRegistry:
    """工厂：注册场景 2（多轮对话）的技能。

    与场景 1 共享 crisis_detector 和 sentiment_skill，另外加入
    场景 2 专用技能（memory_recall、entity_tracker）。
    """
    from app.domain.skills.crisis_detector import CrisisDetectorSkill
    from app.domain.skills.entity_tracker_skill import EntityTrackerSkill
    from app.domain.skills.memory_recall_skill import MemoryRecallSkill
    from app.domain.skills.sentiment_skill import SentimentSkill

    registry = SkillRegistry(tracer=tracer)
    for skill in (
        CrisisDetectorSkill(),
        SentimentSkill(),
        MemoryRecallSkill(),
        EntityTrackerSkill(),
    ):
        registry.register(skill)
    return registry
