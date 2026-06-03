"""Empathy Worker Agent — emotional companionship and crisis-safe responses.

Migrated from V1 ``agents/empathy_agent.py``. V2 changes:

* All dependencies are injected: the LLM (:class:`~app.shared.llm.LLMClient`),
  the shared :class:`~app.shared.emotion_estimator.EmotionEstimator` (no
  re-implemented keyword lexicon — that duplication was 坏味 3 in V1), the
  shared :class:`~app.domain.knowledge.store.DomainKnowledgeStore`, and an
  :class:`~app.shared.tracing.LLMCallTracer`.
* No ``SessionLocal()`` / ``ChatOpenAI()`` / ``os.getenv`` inside the agent.
* ``run`` is async (awaits ``ainvoke``) so it joins the B-9 parallel fan-out;
  ``fallback`` is synchronous and never touches the LLM.
* PromptTuner is *not* wired here (B-9 concern); instead ``run`` accepts an
  optional ``style_fragment`` the Supervisor can pass per request.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.domain.agents.prompts import (
    EMPATHY_BASE,
    EMPATHY_CRISIS_BLOCK,
    EMPATHY_CRISIS_FALLBACK,
    EMPATHY_FALLBACKS,
    EMPATHY_GUIDELINES,
    EMPATHY_RESPONSE_LENGTH,
    EMPATHY_STYLE_INSTRUCTIONS,
)
from app.domain.agents.state import MultiAgentState, extract_token_usage
from app.domain.knowledge.store import DomainKnowledgeStore
from app.domain.skills.crisis_detector import CRISIS_RESOURCES
from app.shared.emotion_estimator import EmotionEstimator
from app.shared.llm import LLMClient, message_text
from app.shared.tracing import LLMCallRecord, LLMCallTracer, NoOpLLMCallTracer

logger = logging.getLogger(__name__)

_DEFAULT_STYLE = "empathetic"
_DOMAIN_KNOWLEDGE_TOP_K = 2
_MAX_EPISODIC_ENTRIES = 5


class EmpathyAgent:
    """Generate a warm, emotion-aware reply, escalating safely on crisis signals."""

    def __init__(
        self,
        llm: LLMClient,
        knowledge: DomainKnowledgeStore,
        *,
        emotion_estimator: EmotionEstimator | None = None,
        tracer: LLMCallTracer | None = None,
        model: str = "",
    ) -> None:
        self._llm = llm
        self._knowledge = knowledge
        self._emotion = emotion_estimator or EmotionEstimator()
        self._tracer = tracer or NoOpLLMCallTracer()
        self._model = model

    async def run(
        self,
        state: MultiAgentState,
        *,
        style_fragment: str | None = None,
    ) -> dict[str, Any]:
        """Produce ``empathy_response`` (+ token usage) for the current diary."""
        diary_content = state.get("diary_content", "")
        intent = state.get("intent", "pure_record")
        profile = state.get("long_term_profile", {}) or {}
        episodic = state.get("episodic_context", []) or []

        is_crisis = self._is_crisis(diary_content, profile)
        preferred_style = str(profile.get("preferred_response_style", _DEFAULT_STYLE))

        domain_knowledge = ""
        if is_crisis or intent in ("emotional_support", "retrospective_review"):
            hits = self._knowledge.query(diary_content[:200], max_results=_DOMAIN_KNOWLEDGE_TOP_K)
            domain_knowledge = "\n".join(hit.content for hit in hits)

        system_prompt = self._build_system_prompt(
            intent=intent,
            preferred_style=preferred_style,
            episodic_context=self._format_episodic(episodic),
            domain_knowledge=domain_knowledge,
            is_crisis=is_crisis,
        )
        if style_fragment:
            system_prompt = f"{system_prompt}\n{style_fragment}"

        prompt = f"{system_prompt}\n\n日记内容：{diary_content}\n\n请给予温暖的回应。"

        started = time.perf_counter()
        try:
            response = await self._llm.ainvoke(prompt)
        except Exception as exc:
            logger.error("empathy.llm_failed: %s", exc)
            self._record_trace(prompt, "", started, str(exc), is_crisis, usage=None)
            return self.fallback(intent, is_crisis=is_crisis)

        reply = message_text(response).strip()
        usage = extract_token_usage(response)
        self._record_trace(prompt, reply, started, None, is_crisis, usage=usage)

        if is_crisis:
            reply = f"{reply}\n\n{CRISIS_RESOURCES}"

        logger.info(
            "empathy.done intent=%s crisis=%s len=%d tokens=%d",
            intent,
            is_crisis,
            len(reply),
            usage["total_tokens_used"],
        )
        return {"empathy_response": reply, **usage}

    def fallback(self, intent: str, *, is_crisis: bool = False) -> dict[str, Any]:
        """Safe, LLM-free reply used when the model is unreachable."""
        if is_crisis:
            reply = f"{EMPATHY_CRISIS_FALLBACK}\n\n{CRISIS_RESOURCES}"
        else:
            reply = EMPATHY_FALLBACKS.get(intent, EMPATHY_FALLBACKS["pure_record"])
        return {"empathy_response": reply}

    def _is_crisis(self, diary_content: str, profile: dict[str, Any]) -> bool:
        content_score = self._emotion.score(diary_content)
        baseline_score = self._baseline_score(profile)
        effective = min(baseline_score, content_score) if content_score < 0 else content_score
        crisis = effective < self._emotion.crisis_threshold
        if crisis:
            logger.warning("empathy.crisis_detected score=%.2f", effective)
        return crisis

    @staticmethod
    def _baseline_score(profile: dict[str, Any]) -> float:
        baseline = profile.get("emotion_baseline", {})
        if isinstance(baseline, dict):
            return float(baseline.get("average_sentiment", 0.0) or 0.0)
        return 0.0

    def _build_system_prompt(
        self,
        *,
        intent: str,
        preferred_style: str,
        episodic_context: str,
        domain_knowledge: str,
        is_crisis: bool,
    ) -> str:
        length = EMPATHY_RESPONSE_LENGTH.get(intent, EMPATHY_RESPONSE_LENGTH["pure_record"])
        style_desc = EMPATHY_STYLE_INSTRUCTIONS.get(
            preferred_style,
            EMPATHY_STYLE_INSTRUCTIONS[_DEFAULT_STYLE],
        )

        parts = [
            EMPATHY_BASE,
            f"\n## 回应风格\n{style_desc}",
            f"\n## 回应长度\n请将回应控制在 {length['min']}-{length['max']} 个汉字之间。",
        ]
        if is_crisis:
            parts.append(EMPATHY_CRISIS_BLOCK)
        if episodic_context:
            parts.append(
                "\n## 之前的交互记忆\n"
                "以下是与用户之前的重要交互记录，请在相关时自然地引用，"
                f"体现你对用户的持续关注和记忆：\n{episodic_context}"
            )
        if domain_knowledge:
            parts.append(
                "\n## 专业知识参考（通用知识，非针对用户的诊断）\n"
                f"以下心理学知识可供参考，如果引用请标注为通用知识参考：\n{domain_knowledge}"
            )
        parts.append(EMPATHY_GUIDELINES)
        return "\n".join(parts)

    @staticmethod
    def _format_episodic(entries: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for entry in entries[:_MAX_EPISODIC_ENTRIES]:
            if not isinstance(entry, dict):
                continue
            parts: list[str] = []
            if entry.get("event"):
                parts.append(f"事件：{entry['event']}")
            if entry.get("emotion"):
                parts.append(f"情绪：{entry['emotion']}")
            if entry.get("ai_suggestion"):
                parts.append(f"当时的建议：{entry['ai_suggestion']}")
            feedback = entry.get("user_feedback", "none")
            if feedback and feedback != "none":
                parts.append(f"用户反馈：{feedback}")
            if parts:
                lines.append("• " + "；".join(parts))
        return "\n".join(lines)

    def _record_trace(
        self,
        prompt: str,
        response: str,
        started: float,
        error: str | None,
        is_crisis: bool,
        *,
        usage: dict[str, int] | None,
    ) -> None:
        tokens_in = 0
        tokens_out = 0
        if usage is not None:
            tokens_in = usage["cache_hit_tokens"] + usage["cache_miss_tokens"]
            tokens_out = usage["output_tokens"]
        self._tracer.record(
            LLMCallRecord(
                agent_name="empathy",
                call_type="generate",
                model=self._model,
                tier="crisis" if is_crisis else "medium",
                prompt=prompt,
                response=response,
                latency_ms=(time.perf_counter() - started) * 1000,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                error=error,
            )
        )


__all__ = ["EmpathyAgent"]
