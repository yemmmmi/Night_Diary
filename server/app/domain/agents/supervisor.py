"""SupervisorAgent — classify intent, integrate skills, route workers, synthesize.

The Supervisor is the hub of the multi-agent pipeline. For each diary turn it:

1. Classifies intent via the injected :class:`IntentClassifier` (async).
2. Calls :meth:`SkillRegistry.select_skills` — the **production call site** that
   turns the B-6 Skill system from dead code into a live dependency. Every
   activation/suppression is recorded (by the registry's tracer) and stamped
   with this turn's ``decision_id`` so ``skill_activations`` rows link back to
   the ``agent_decisions`` row written here.
3. Detects crisis through the shared :class:`EmotionEstimator` (the same source
   the ``crisis_detector`` skill and ``EmpathyAgent`` use — no third copy of the
   lexicon). A crisis short-circuits routing to EmpathyAgent only.
4. Derives an execution ``tier`` (light/medium/heavy/crisis) and token budget.
5. Routes to the worker set for the intent (low-confidence → safest empathy-only
   path, per architecture decision #15).

It exposes two async coroutines the graph runs as nodes: :meth:`classify`
(before the worker fan-out) and :meth:`synthesize` (after). LangGraph is **not**
used — :mod:`app.domain.agents.graph` drives these with plain ``asyncio``.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from app.domain.agents.intent_classifier import IntentClassifier
from app.domain.agents.prompts import (
    SUPERVISOR_FALLBACK_RESPONSE,
    SUPERVISOR_SYNTHESIZE_PROMPT,
    SUPERVISOR_WORKER_LABELS,
)
from app.domain.agents.state import MultiAgentState, extract_token_usage
from app.domain.agents.types import IntentCategory, IntentResult
from app.domain.skills.registry import SkillRegistry
from app.domain.skills.types import SkillProfileContext
from app.shared.crisis_guard import CrisisGuard, get_crisis_guard
from app.shared.emotion_estimator import EmotionEstimator, get_emotion_estimator
from app.shared.llm import LLMClient, message_text
from app.shared.pipeline_trace import trace_span
from app.shared.tracing import (
    AgentDecisionLogger,
    AgentDecisionRecord,
    LLMCallRecord,
    LLMCallTracer,
    NoOpAgentDecisionLogger,
    NoOpLLMCallTracer,
)

logger = logging.getLogger(__name__)

# Token budget per intent (min, max); the midpoint is allocated. Migrated from V1.
TOKEN_BUDGET_MAP: dict[str, tuple[int, int]] = {
    IntentCategory.PURE_RECORD.value: (400, 600),
    IntentCategory.EMOTIONAL_SUPPORT.value: (1000, 1500),
    IntentCategory.RETROSPECTIVE_REVIEW.value: (1500, 2500),
    IntentCategory.HABIT_TRACKING.value: (1200, 2000),
}
DEFAULT_TOKEN_BUDGET = 800
CRISIS_TOKEN_BUDGET = 300

# Intent → worker set. Workers run in two phases by the graph (retrieval first).
INTENT_ROUTING: dict[str, tuple[str, ...]] = {
    IntentCategory.PURE_RECORD.value: ("empathy",),
    IntentCategory.EMOTIONAL_SUPPORT.value: ("empathy", "retrieval"),
    IntentCategory.RETROSPECTIVE_REVIEW.value: ("empathy", "retrieval", "insight"),
    IntentCategory.HABIT_TRACKING.value: ("retrieval", "insight"),
}
CRISIS_AGENTS: tuple[str, ...] = ("empathy",)
DEFAULT_AGENTS: tuple[str, ...] = ("empathy",)

# Intent → tier label (crisis is handled separately).
TIER_BY_INTENT: dict[str, str] = {
    IntentCategory.PURE_RECORD.value: "light",
    IntentCategory.EMOTIONAL_SUPPORT.value: "medium",
    IntentCategory.RETROSPECTIVE_REVIEW.value: "heavy",
    IntentCategory.HABIT_TRACKING.value: "heavy",
}

# Below this classifier confidence, fall back to the safest path (empathy only).
LOW_CONFIDENCE_THRESHOLD = 0.5
# Budget given to the skill registry's greedy selection (how much context skills
# may add); independent of the response token budget.
SKILL_SELECTION_BUDGET = 4000

CRISIS_DETECTOR_SKILL = "crisis_detector"


def allocate_token_budget(intent: str, *, is_crisis: bool = False) -> int:
    """Return the response token budget for an intent (crisis is capped low)."""
    if is_crisis:
        return CRISIS_TOKEN_BUDGET
    budget_range = TOKEN_BUDGET_MAP.get(intent)
    if budget_range is None:
        return DEFAULT_TOKEN_BUDGET
    low, high = budget_range
    return (low + high) // 2


class SupervisorAgent:
    """Classify, integrate skills, route workers, and synthesize the final reply."""

    def __init__(
        self,
        intent_classifier: IntentClassifier,
        skill_registry: SkillRegistry,
        *,
        llm: LLMClient | None = None,
        emotion_estimator: EmotionEstimator | None = None,
        crisis_guard: CrisisGuard | None = None,
        decision_logger: AgentDecisionLogger | None = None,
        llm_tracer: LLMCallTracer | None = None,
        model: str = "",
    ) -> None:
        self._classifier = intent_classifier
        self._skills = skill_registry
        self._llm = llm
        self._emotion = emotion_estimator or get_emotion_estimator()
        self._crisis_guard = crisis_guard or get_crisis_guard()
        self._decisions = decision_logger or NoOpAgentDecisionLogger()
        self._tracer = llm_tracer or NoOpLLMCallTracer()
        self._model = model

    # ----- node 1: classify + skill selection + routing -----

    async def classify(self, state: MultiAgentState) -> dict[str, Any]:
        """Decide intent, tier, budget, activated agents and skills for this turn."""
        diary_content = state.get("diary_content", "")
        diary_id = state.get("diary_id", "")
        profile = state.get("long_term_profile", {}) or {}

        with trace_span(
            "S4a_intent",
            "意图分类",
            input_snapshot={"diary_id": diary_id, "content_len": len(diary_content)},
        ) as span:
            intent_result = await self._safe_classify(diary_content)
            intent = intent_result.intent_category or IntentCategory.PURE_RECORD.value
            if span:
                span.set_output(
                    {"intent": intent, "confidence": intent_result.confidence}
                )

        decision_id = uuid.uuid4().hex
        skill_context = self._skill_context(intent, profile)
        with trace_span(
            "S4b_skills",
            "技能选择",
            input_snapshot={"intent": intent},
        ) as span:
            selected = self._skills.select_skills(
                diary_content,
                skill_context,
                token_budget=SKILL_SELECTION_BUDGET,
                decision_id=decision_id,
            )
            activated_skills = [skill.metadata.name for skill in selected]
            if span:
                span.set_output({"activated_skills": activated_skills})

        with trace_span(
            "S4c_crisis",
            "危机检测",
            input_snapshot={"diary_id": diary_id},
        ) as span:
            is_crisis = self._detect_crisis(diary_content)
            if span:
                span.set_output({"is_crisis": is_crisis})

        tier = "crisis" if is_crisis else TIER_BY_INTENT.get(intent, "light")
        token_budget = allocate_token_budget(intent, is_crisis=is_crisis)
        with trace_span(
            "S4d_route",
            "路由决策",
            input_snapshot={"intent": intent, "is_crisis": is_crisis},
        ) as span:
            activated_agents = self._route(
                intent,
                is_crisis,
                intent_result.confidence,
                need_retrieval=intent_result.need_retrieval,
            )
            if span:
                span.set_output(
                    {"activated_agents": list(activated_agents), "tier": tier}
                )

        self._log_decisions(
            diary_id=diary_id,
            intent=intent,
            tier=tier,
            confidence=intent_result.confidence,
            activated_agents=activated_agents,
            activated_skills=tuple(activated_skills),
            is_crisis=is_crisis,
            decision_id=decision_id,
        )

        logger.info(
            "supervisor.classify intent=%s tier=%s crisis=%s budget=%d agents=%s skills=%s",
            intent,
            tier,
            is_crisis,
            token_budget,
            activated_agents,
            activated_skills,
        )
        return {
            "intent": intent,
            "tier": tier,
            "token_budget": token_budget,
            "activated_agents": list(activated_agents),
            "activated_skills": activated_skills,
            "agent_mode": "multi_agent",
        }

    # ----- node 2: synthesize -----

    async def synthesize(self, state: MultiAgentState) -> dict[str, Any]:
        """Merge worker outputs into one final reply, tolerating partial failures."""
        tier = state.get("tier", "")
        outputs = self._collect_outputs(state)
        errors = state.get("errors", [])
        if errors:
            logger.warning(
                "supervisor.synthesize degraded: %d error(s), %d output(s)",
                len(errors),
                len(outputs),
            )

        if not outputs:
            logger.error("supervisor.synthesize all workers empty, using fallback")
            return {"final_response": SUPERVISOR_FALLBACK_RESPONSE, "agent_mode": "multi_agent"}

        # Crisis: the empathy reply already carries the safety resources verbatim;
        # never reshape it through another LLM call.
        if tier == "crisis" and "empathy" in outputs:
            return {"final_response": outputs["empathy"], "agent_mode": "multi_agent"}

        # Only call LLM synthesize when multiple content-producing workers
        # (empathy + insight) need merging. retrieval_context was already
        # consumed by empathy/insight during generation, so merging it again
        # is redundant work.
        content_outputs = {k: v for k, v in outputs.items() if k != "retrieval"}

        with trace_span(
            "S5_synthesize_core",
            "合成逻辑",
            input_snapshot={"content_count": len(content_outputs), "tier": tier},
        ) as span:
            if self._llm is not None and len(content_outputs) > 1:
                final_response, usage = await self._llm_synthesize(outputs, state)
                if span:
                    span.set_output({"method": "llm", "length": len(final_response)})
                return {"final_response": final_response, "agent_mode": "multi_agent", **usage}

            # Single content worker — its output is already the final reply.
            if len(content_outputs) == 1:
                final = next(iter(content_outputs.values()))
                if span:
                    span.set_output({"method": "single", "length": len(final)})
                return {
                    "final_response": final,
                    "agent_mode": "multi_agent",
                }

            # Multiple content workers but no LLM available, or only retrieval
            # produced output — fall back to simple join.
            final = self._simple_synthesize(outputs)
            if span:
                span.set_output({"method": "simple_join", "length": len(final)})
            return {
                "final_response": final,
                "agent_mode": "multi_agent",
            }

    async def synthesize_streaming(
        self,
        state: MultiAgentState,
        *,
        workers: dict[str, Any] | None = None,
        trace_id: str = "",
    ) -> AsyncGenerator[str, None]:
        """Streaming synthesis — single content worker astreams, multi-worker degrades.

        For the ~75% scene-1 single-worker routes (PURE_RECORD /
        EMOTIONAL_SUPPORT / HABIT_TRACKING) there is exactly one content-producing
        worker, so its reply can be streamed token-by-token via the worker's
        :meth:`run_streaming` — no LLM merge is needed. The RETROSPECTIVE_REVIEW
        route has two content workers (empathy + insight) and cannot be streamed
        without an LLM synthesis pass, so it degrades to the non-streaming
        :meth:`synthesize` and emits the merged reply in a single chunk.

        ``workers`` maps worker names ("empathy" / "insight") to agent instances
        that expose ``run_streaming``. The :class:`MultiAgentGraph` owns the
        worker agents and passes them in — the supervisor itself stays
        worker-agnostic, exactly as in V2 (it has no ``_workers`` of its own).
        When a single-worker route is requested but no streaming-capable worker is
        supplied, the worker's already-computed output is emitted verbatim so the
        caller always receives a complete reply.
        """
        if trace_id:
            logger.debug("supervisor.synthesize_streaming trace_id=%s", trace_id)

        outputs = self._collect_outputs(state)
        content_outputs = {k: v for k, v in outputs.items() if k != "retrieval"}

        if len(content_outputs) == 1:
            worker_name = next(iter(content_outputs))
            worker = (workers or {}).get(worker_name)
            if worker is not None and hasattr(worker, "run_streaming"):
                async for token in worker.run_streaming(state):
                    yield token
                return
            # Worker lacks streaming support — emit the already-computed output.
            yield content_outputs[worker_name]
            return

        # Multiple content workers (e.g. RETROSPECTIVE_REVIEW) — degrade to the
        # non-streaming LLM synthesis and emit the merged reply in one chunk.
        result = await self.synthesize(state)
        yield result.get("final_response", "")

    # ----- internals -----

    async def _safe_classify(self, diary_content: str) -> IntentResult:
        try:
            return await self._classifier.classify(diary_content)
        except Exception as exc:
            logger.error("supervisor.classify_failed, defaulting to pure_record: %s", exc)
            return IntentResult(
                intent_category=IntentCategory.PURE_RECORD.value,
                confidence=0.5,
            )

    @staticmethod
    def _skill_context(intent: str, profile: dict[str, Any]) -> SkillProfileContext:
        context: SkillProfileContext = {"intent": intent}
        topics = profile.get("recurring_topics")
        if isinstance(topics, list):
            context["recurring_topics"] = [str(t) for t in topics]
        return context

    def _detect_crisis(self, diary_content: str) -> bool:
        """Delegate to the shared CrisisGuard (same logic, single source of truth)."""
        return self._crisis_guard.detect(diary_content)

    @staticmethod
    def _route(
        intent: str,
        is_crisis: bool,
        confidence: float,
        *,
        need_retrieval: bool = True,
    ) -> tuple[str, ...]:
        """Route to workers based on intent, crisis state, and retrieval need.

        ``need_retrieval`` defaults to ``True`` so that the intent-based routing
        table is honoured when the classifier doesn't explicitly signal that
        retrieval is unnecessary. When ``False``, the ``retrieval`` worker is
        stripped — e.g. a short emotional vent ("今天好累") classified as
        ``emotional_support`` without temporal references doesn't need RAG.
        """
        if is_crisis:
            return CRISIS_AGENTS
        if confidence < LOW_CONFIDENCE_THRESHOLD:
            return DEFAULT_AGENTS
        base = INTENT_ROUTING.get(intent, DEFAULT_AGENTS)
        if not need_retrieval:
            stripped = tuple(a for a in base if a != "retrieval")
            return stripped if stripped else DEFAULT_AGENTS
        return base

    def _log_decisions(
        self,
        *,
        diary_id: str,
        intent: str,
        tier: str,
        confidence: float,
        activated_agents: tuple[str, ...],
        activated_skills: tuple[str, ...],
        is_crisis: bool,
        decision_id: str,
    ) -> None:
        self._decisions.record(
            AgentDecisionRecord(
                agent_name="supervisor",
                decision_type="intent_classification",
                diary_id=diary_id,
                intent=intent,
                reasoning=f"confidence={confidence:.2f}; crisis={is_crisis}",
            )
        )
        # The skill_activation decision shares its id with the SkillActivationRecord
        # rows (decision_id) so the activations link back to this row.
        self._decisions.record(
            AgentDecisionRecord(
                id=decision_id,
                agent_name="supervisor",
                decision_type="skill_activation",
                diary_id=diary_id,
                intent=intent,
                tier=tier,
                skill_ids=activated_skills,
                reasoning=f"activated_skills={list(activated_skills)}",
            )
        )
        self._decisions.record(
            AgentDecisionRecord(
                agent_name="supervisor",
                decision_type="tier_routing",
                diary_id=diary_id,
                intent=intent,
                tier=tier,
                reasoning=f"tier={tier}",
            )
        )
        self._decisions.record(
            AgentDecisionRecord(
                agent_name="supervisor",
                decision_type="worker_routing",
                diary_id=diary_id,
                intent=intent,
                tier=tier,
                reasoning=f"activated_agents={list(activated_agents)}",
            )
        )

    @staticmethod
    def _collect_outputs(state: MultiAgentState) -> dict[str, str]:
        outputs: dict[str, str] = {}
        for key, field in (
            ("retrieval", "retrieval_context"),
            ("empathy", "empathy_response"),
            ("insight", "insight_response"),
        ):
            value = str(state.get(field, "") or "").strip()
            if value:
                outputs[key] = value
        return outputs

    async def _llm_synthesize(
        self,
        outputs: dict[str, str],
        state: MultiAgentState,
    ) -> tuple[str, dict[str, int]]:
        outputs_text = "".join(
            f"【{SUPERVISOR_WORKER_LABELS.get(name, name)}】\n{text}\n\n"
            for name, text in outputs.items()
        )
        intent = state.get("intent", IntentCategory.PURE_RECORD.value)
        token_budget = state.get("token_budget", DEFAULT_TOKEN_BUDGET)
        max_chars = min(300, token_budget // 3)
        prompt = SUPERVISOR_SYNTHESIZE_PROMPT.format(
            intent=intent,
            outputs_text=outputs_text,
            max_chars=max_chars,
        )

        started = time.perf_counter()
        try:
            response = await self._llm.ainvoke(prompt)  # type: ignore[union-attr]
        except Exception as exc:
            logger.warning("supervisor.synthesize_llm_failed, simple join: %s", exc)
            self._record_synthesis_trace(prompt, "", started, str(exc), state)
            return self._simple_synthesize(outputs), {}

        final = message_text(response).strip()
        usage = extract_token_usage(response)
        self._record_synthesis_trace(prompt, final, started, None, state, usage=usage)
        return final, usage

    @staticmethod
    def _simple_synthesize(outputs: dict[str, str]) -> str:
        parts = [outputs[name] for name in ("empathy", "insight", "retrieval") if name in outputs]
        return "\n\n".join(parts)

    def _record_synthesis_trace(
        self,
        prompt: str,
        response: str,
        started: float,
        error: str | None,
        state: MultiAgentState,
        *,
        usage: dict[str, int] | None = None,
    ) -> None:
        tokens_in = 0
        tokens_out = 0
        if usage is not None:
            tokens_in = usage["cache_hit_tokens"] + usage["cache_miss_tokens"]
            tokens_out = usage["output_tokens"]
        self._tracer.record(
            LLMCallRecord(
                agent_name="supervisor",
                call_type="synthesize",
                model=self._model,
                tier=str(state.get("tier", "")),
                prompt=prompt,
                response=response,
                latency_ms=(time.perf_counter() - started) * 1000,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                error=error,
            )
        )


__all__ = [
    "SupervisorAgent",
    "allocate_token_budget",
]
