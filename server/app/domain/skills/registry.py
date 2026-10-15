"""SkillRegistry — register and select skills for one diary analysis.

Two-stage activation scoring (rule floor → light-LLM semantic rescue):

1. **Rule stage (floor).** Every skill's keyword/intent heuristic runs first;
   scores >= ``ACTIVATION_THRESHOLD`` activate directly — the hot path spends
   zero LLM tokens. A crisis severe signal scores 1.0 here and is therefore
   unreachable by any later stage (layer 0/1 of the crisis layered defense).
2. **LLM rescue stage (semantic long-tail).** Keyword matching is an inherent
   overfit: a user's phrasing may genuinely need a skill without hitting the
   prepared lexicon. Only skills scoring BELOW threshold while the turn's
   intent is a weak-signal one (emotion / retrospective / advice / entity
   flavours) enter the grey list, and ONE light LLM call scores the whole
   list. Fusion is ``max(rule_score, llm_score)`` — the LLM can only rescue
   a missed activation, never veto a rule hit. Any LLM failure, timeout, or
   ``llm=None`` degrades to the pure-rule result; stage 2 can never break the
   selection chain.

Grey-list provenance is encoded into ``SkillActivationRecord.reason``
(``source=rule | llm_rescue`` plus the per-stage scores) — a Text column, so
no schema migration is needed.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from app.domain.skills.base import ACTIVATION_THRESHOLD, BaseSkill
from app.domain.skills.types import SkillProfileContext
from app.shared.llm import LLMClient, message_text
from app.shared.tracing import (
    NoOpSkillActivationTracer,
    SkillActivationRecord,
    SkillActivationTracer,
)

logger = logging.getLogger(__name__)

#: Intents that warrant the stage-2 LLM rescue for sub-threshold skills. The
#: diary (scene 1) and chat (scene 2) equivalents are both listed. Everything
#: else (pure_record / casual_chat / task-shaped intents) stays pure-rule —
#: zero LLM cost on the hot path.
LLM_RESCUE_INTENTS: frozenset[str] = frozenset(
    {
        "emotional_support",
        "emotional_vent",
        "retrospective_review",
        "retrospective_query",
        "advice_seeking",
        "entity_query",
    }
)

_RESCUE_LLM_PROMPT = """规则关键词没有命中，但用户表达的内容可能仍然需要以下技能。请根据用户实际表达的含义和情绪判断，为每个技能给出 0.0 到 1.0 的激活分数。

技能列表：
{catalog}

用户文本：{content}

分数含义：0.3 以上表示应该激活来处理这段文本；0.0 表示完全不相关。不要只依赖字面关键词匹配，要理解文本的语义。

只输出一个 JSON（每个技能一项，key 为技能 name，value 为分数），不要任何其他内容。"""


def _parse_rescue_scores(answer: str) -> dict[str, float]:
    """Parse the rescue LLM reply into ``{skill_name: score}``.

    Mirrors the tolerant parsing used by the intent router: code fences are
    stripped, a bare ``{...}`` block is regex-extracted when the reply has
    surrounding prose, and garbage values are dropped (the affected skill
    then keeps its rule score).
    """
    cleaned = (answer or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    data: Any = None
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError, TypeError):
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
            except (json.JSONDecodeError, ValueError, TypeError):
                data = None

    scores: dict[str, float] = {}
    if not isinstance(data, dict):
        return scores
    for name, value in data.items():
        try:
            scores[str(name)] = max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            continue
    return scores


class SkillRegistry:
    """Manage skills and greedily select activated ones under a token budget."""

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
        llm: LLMClient | None = None,
    ) -> list[BaseSkill]:
        """Greedy selection by activation_score * priority within token budget.

        Two-stage scoring: rules first (floor), then one light LLM call that
        can only *raise* grey-listed skills (``max`` fusion — never a veto).
        ``llm=None`` or any stage-2 failure keeps the result identical to the
        pure-rule path.

        ``decision_id`` (when given) is stamped onto every
        :class:`SkillActivationRecord` so the rows link back to the owning
        ``agent_decisions`` entry (the Supervisor passes its decision id in B-9).
        """
        if not self._skills or token_budget <= 0:
            return []

        candidates: list[tuple[float, BaseSkill]] = []
        grey: list[tuple[BaseSkill, float]] = []
        grey_latencies: dict[str, float] = {}
        digest = text[:200]
        intent = (profile or {}).get("intent", "pure_record")

        # ── Stage 1: rule floor (zero LLM cost on the hot path) ──
        for skill in self._skills.values():
            started = time.perf_counter()
            try:
                score = skill.activation_score(text, profile)
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
            if score >= ACTIVATION_THRESHOLD:
                self._tracer.record(
                    SkillActivationRecord(
                        skill_name=skill.metadata.name,
                        score=score,
                        threshold=ACTIVATION_THRESHOLD,
                        activated=True,
                        reason=self._rule_reason(skill, score, True, intent),
                        input_digest=digest,
                        latency_ms=latency_ms,
                        decision_id=decision_id,
                    )
                )
                candidates.append((score * skill.metadata.priority, skill))
            elif intent in LLM_RESCUE_INTENTS:
                # Grey list: rules missed, but the intent smells like the
                # skill's lane — worth one light LLM look (stage 2).
                grey.append((skill, score))
                grey_latencies[skill.metadata.name] = latency_ms
            else:
                self._tracer.record(
                    SkillActivationRecord(
                        skill_name=skill.metadata.name,
                        score=score,
                        threshold=ACTIVATION_THRESHOLD,
                        activated=False,
                        reason=self._rule_reason(skill, score, False, intent),
                        input_digest=digest,
                        latency_ms=latency_ms,
                        decision_id=decision_id,
                    )
                )
                logger.debug(
                    "Skill '%s' suppressed score=%.2f threshold=%.2f",
                    skill.metadata.name,
                    score,
                    ACTIVATION_THRESHOLD,
                )

        # ── Stage 2: light-LLM rescue for the grey list (max fusion) ──
        if grey:
            rescued = self._rescue_grey_skills(
                text,
                intent,
                grey,
                llm,
                digest=digest,
                decision_id=decision_id,
                latencies=grey_latencies,
            )
            candidates.extend(rescued)

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

    def _rescue_grey_skills(
        self,
        text: str,
        intent: str,
        grey: list[tuple[BaseSkill, float]],
        llm: LLMClient | None,
        *,
        digest: str,
        decision_id: str,
        latencies: dict[str, float],
    ) -> list[tuple[float, BaseSkill]]:
        """Score the grey list with one light LLM call and max-fuse.

        Fusion is ``max(rule_score, llm_score)`` so the LLM can only rescue a
        missed activation — it can never suppress what the rules would have
        caught (this is what keeps the crisis layer single-directional).
        Any LLM failure or ``llm=None`` degrades every grey skill to its
        pure-rule outcome.
        """
        rescued: dict[str, float] = {}
        rescue_error = ""
        if llm is None:
            rescue_error = "no_llm"
        else:
            catalog = "\n".join(
                f"- {skill.metadata.name}：{skill.metadata.description}"
                f"（触发提示：{'、'.join(skill.metadata.triggers[:8])}）"
                for skill, _ in grey
            )
            prompt = _RESCUE_LLM_PROMPT.format(content=text[:500], catalog=catalog)
            try:
                response = llm.invoke(prompt)
                rescued = _parse_rescue_scores(message_text(response))
                if rescued:
                    logger.info("Skill rescue llm scores=%s", rescued)
            except Exception as exc:
                rescue_error = f"error: {exc}"
                logger.info("Skill rescue LLM failed (degrade to rules): %s", exc)

        extra: list[tuple[float, BaseSkill]] = []
        for skill, rule_score in grey:
            name = skill.metadata.name
            llm_score = rescued.get(name)
            final = rule_score if llm_score is None else max(rule_score, llm_score)
            activated = final >= ACTIVATION_THRESHOLD
            self._tracer.record(
                SkillActivationRecord(
                    skill_name=name,
                    score=final,
                    threshold=ACTIVATION_THRESHOLD,
                    activated=activated,
                    reason=self._rescue_reason(
                        skill, rule_score, llm_score, final, activated, intent, rescue_error
                    ),
                    input_digest=digest,
                    latency_ms=latencies.get(name, 0.0),
                    decision_id=decision_id,
                )
            )
            if activated:
                extra.append((final * skill.metadata.priority, skill))
                logger.info(
                    "Rescued skill name=%s rule=%.2f llm=%s final=%.2f",
                    name,
                    rule_score,
                    f"{llm_score:.2f}" if llm_score is not None else "n/a",
                    final,
                )
            else:
                logger.debug(
                    "Skill '%s' stays suppressed after rescue final=%.2f threshold=%.2f",
                    name,
                    final,
                    ACTIVATION_THRESHOLD,
                )
        return extra

    @staticmethod
    def _rule_reason(
        skill: BaseSkill,
        score: float,
        activated: bool,
        intent: str,
    ) -> str:
        status = "activated" if activated else "suppressed"
        return (
            f"{status}; source=rule; score={score:.2f}; "
            f"threshold={ACTIVATION_THRESHOLD}; intent={intent}; "
            f"skill={skill.metadata.name}"
        )

    @staticmethod
    def _rescue_reason(
        skill: BaseSkill,
        rule_score: float,
        llm_score: float | None,
        final: float,
        activated: bool,
        intent: str,
        rescue_error: str,
    ) -> str:
        status = "activated" if activated else "suppressed"
        if llm_score is None:
            # Grey-listed but the rescue never produced a score for this
            # skill (no llm / call failed / unparseable reply).
            detail = f"llm_rescue={rescue_error or 'no_score'}"
            source = "rule"
        else:
            source = "llm_rescue"
            detail = f"rule_score={rule_score:.2f}; llm_score={llm_score:.2f}"
        return (
            f"{status}; source={source}; {detail}; final={final:.2f}; "
            f"threshold={ACTIVATION_THRESHOLD}; intent={intent}; "
            f"skill={skill.metadata.name}"
        )


def create_default_registry(
    tracer: SkillActivationTracer | None = None,
) -> SkillRegistry:
    """Factory: register all MVP skills for standalone testing.

    The skill framework (BaseSkill, SkillRegistry, this factory) is extensible —
    new skills subclass BaseSkill and are registered here. Stub placeholders
    were removed; only activated MVP skills remain.
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
    """Factory: register skills for scene 1 (diary analysis).

    Shares crisis_detector and sentiment_skill with the default registry, plus
    memory_recall for retrospective diary entries (e.g. "上周和朋友去了公园"
    triggers memory retrieval of related past events).
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
    """Factory: register skills for scene 2 (multi-turn conversation).

    Shares crisis_detector and sentiment_skill with scene 1, plus
    scene-2-specific skills (memory_recall, entity_tracker).
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
