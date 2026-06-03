"""Insight Worker Agent — pattern discovery, trend analysis, weekly/monthly reports.

Migrated from V1 ``agents/insight_agent.py``. V2 changes:

* DI for the LLM (:class:`~app.shared.llm.LLMClient`), the shared
  :class:`~app.domain.knowledge.store.DomainKnowledgeStore` and an
  :class:`~app.shared.tracing.LLMCallTracer`. No ``SessionLocal()`` /
  ``ChatOpenAI()`` inside the agent.
* ``run`` is async (awaits ``ainvoke``); ``fallback`` is synchronous.
* PromptTuner stays in B-9; ``run`` accepts an optional ``style_fragment``.
* Emotion-baseline comparison reuses :class:`~app.domain.memory.types.EmotionBaseline`.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.domain.agents.prompts import (
    INSIGHT_FALLBACK,
    INSIGHT_REPORT_SYSTEM,
    INSIGHT_SYSTEM,
)
from app.domain.agents.state import MultiAgentState, extract_token_usage
from app.domain.knowledge.store import DomainKnowledgeStore
from app.domain.memory.types import EmotionBaseline
from app.shared.llm import LLMClient, message_text
from app.shared.tracing import LLMCallRecord, LLMCallTracer, NoOpLLMCallTracer

logger = logging.getLogger(__name__)

EMOTION_DEVIATION_THRESHOLD = 0.3
_DOMAIN_KNOWLEDGE_TOP_K = 2
_MAX_EPISODIC_ENTRIES = 5

_REPORT_KEYWORDS_WEEKLY = ("周报", "这周", "本周", "一周", "过去七天", "过去7天", "weekly")
_REPORT_KEYWORDS_MONTHLY = ("月报", "这个月", "本月", "一个月", "过去三十天", "过去30天", "monthly")

_NEGATIVE_EMOTIONS = ("焦虑", "悲伤", "愤怒", "沮丧", "失落", "压力", "疲惫", "孤独")
_POSITIVE_EMOTIONS = ("开心", "满足", "兴奋", "感恩", "平静", "希望", "自信")


class InsightAgent:
    """Analyse emotional patterns/trends and produce actionable insight or reports."""

    def __init__(
        self,
        llm: LLMClient,
        knowledge: DomainKnowledgeStore,
        *,
        tracer: LLMCallTracer | None = None,
        model: str = "",
    ) -> None:
        self._llm = llm
        self._knowledge = knowledge
        self._tracer = tracer or NoOpLLMCallTracer()
        self._model = model

    async def run(
        self,
        state: MultiAgentState,
        *,
        style_fragment: str | None = None,
    ) -> dict[str, Any]:
        """Produce ``insight_response`` (+ token usage) for the current diary."""
        diary_content = state.get("diary_content", "")
        retrieval_context = state.get("retrieval_context", "")
        episodic = state.get("episodic_context", []) or []
        profile = state.get("long_term_profile", {}) or {}

        report_type = self._detect_report_type(diary_content)
        system_prompt = self._system_prompt(report_type)
        if style_fragment:
            system_prompt = f"{system_prompt}\n{style_fragment}"

        deviation = self._detect_emotion_deviation(profile, episodic)
        domain_knowledge = "\n".join(
            hit.content
            for hit in self._knowledge.query(diary_content[:100], max_results=_DOMAIN_KNOWLEDGE_TOP_K)
        )
        user_message = self._build_user_message(
            diary_content=diary_content,
            retrieval_context=retrieval_context,
            episodic=episodic,
            profile=profile,
            domain_knowledge=domain_knowledge,
            deviation=deviation,
        )
        prompt = f"{system_prompt}\n\n{user_message}"

        started = time.perf_counter()
        try:
            response = await self._llm.ainvoke(prompt)
        except Exception as exc:
            logger.error("insight.llm_failed: %s", exc)
            self._record_trace(prompt, "", started, str(exc), usage=None)
            return self.fallback()

        reply = message_text(response).strip()
        usage = extract_token_usage(response)
        self._record_trace(prompt, reply, started, None, usage=usage)

        logger.info(
            "insight.done report=%s deviation=%s len=%d tokens=%d",
            report_type or "none",
            "yes" if deviation else "no",
            len(reply),
            usage["total_tokens_used"],
        )
        return {"insight_response": reply, **usage}

    def fallback(self) -> dict[str, Any]:
        """Safe, LLM-free reply used when the model is unreachable."""
        return {"insight_response": INSIGHT_FALLBACK}

    @staticmethod
    def _detect_report_type(content: str) -> str | None:
        lowered = content.lower()
        if any(kw in lowered for kw in _REPORT_KEYWORDS_MONTHLY):
            return "monthly"
        if any(kw in lowered for kw in _REPORT_KEYWORDS_WEEKLY):
            return "weekly"
        return None

    @staticmethod
    def _system_prompt(report_type: str | None) -> str:
        if report_type is None:
            return INSIGHT_SYSTEM
        if report_type == "weekly":
            return INSIGHT_REPORT_SYSTEM.format(report_type="周报", period="周")
        return INSIGHT_REPORT_SYSTEM.format(report_type="月报", period="月")

    def _detect_emotion_deviation(
        self,
        profile: dict[str, Any],
        episodic: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if not episodic:
            return None

        baseline_data = profile.get("emotion_baseline", {}) or {}
        baseline = EmotionBaseline(
            average_sentiment=float(baseline_data.get("average_sentiment", 0.0) or 0.0),
            volatility=float(baseline_data.get("volatility", 0.0) or 0.0),
            dominant_emotion=str(baseline_data.get("dominant_emotion", "neutral")),
        )

        recent: list[float] = []
        for entry in episodic:
            if not isinstance(entry, dict):
                continue
            importance = float(entry.get("importance", 0.5) or 0.5)
            emotion = entry.get("emotion", "")
            if emotion in _NEGATIVE_EMOTIONS:
                recent.append(-0.6 * importance)
            elif emotion in _POSITIVE_EMOTIONS:
                recent.append(0.6 * importance)
            else:
                recent.append(0.0)

        if not recent:
            return None

        recent_avg = sum(recent) / len(recent)
        deviation = recent_avg - baseline.average_sentiment
        if abs(deviation) >= EMOTION_DEVIATION_THRESHOLD:
            return {
                "direction": "lower" if deviation < 0 else "higher",
                "magnitude": abs(deviation),
            }
        return None

    def _build_user_message(
        self,
        *,
        diary_content: str,
        retrieval_context: str,
        episodic: list[dict[str, Any]],
        profile: dict[str, Any],
        domain_knowledge: str,
        deviation: dict[str, Any] | None,
    ) -> str:
        parts = [f"【当前日记】\n{diary_content}"]

        context_summary = self._context_summary(retrieval_context, episodic, profile)
        if context_summary:
            parts.append(context_summary)
        if domain_knowledge:
            parts.append(f"【专业知识参考】\n{domain_knowledge}")
        if deviation:
            direction_text = "低于" if deviation["direction"] == "lower" else "高于"
            parts.append(
                "【情绪偏离提醒】\n"
                f"用户近期情绪显著{direction_text}其历史基线"
                f"（偏离幅度: {deviation['magnitude']:.2f}）。"
                "请在分析中温和地指出这一变化，并提供应对策略。"
            )
        return "\n\n".join(parts)

    @staticmethod
    def _context_summary(
        retrieval_context: str,
        episodic: list[dict[str, Any]],
        profile: dict[str, Any],
    ) -> str:
        parts: list[str] = []
        if retrieval_context:
            parts.append(f"【历史日记摘要】\n{retrieval_context}")

        memory_lines: list[str] = []
        for entry in episodic[:_MAX_EPISODIC_ENTRIES]:
            if not isinstance(entry, dict) or not entry.get("event"):
                continue
            line = f"- {entry['event']}"
            if entry.get("emotion"):
                line += f"（情绪: {entry['emotion']}）"
            if entry.get("ai_suggestion"):
                line += f" → 建议: {entry['ai_suggestion']}"
            memory_lines.append(line)
        if memory_lines:
            parts.append("【近期重要记忆】\n" + "\n".join(memory_lines))

        profile_parts: list[str] = []
        topics = profile.get("recurring_topics", [])
        if topics:
            profile_parts.append(f"反复话题: {', '.join(topics[:5])}")
        tags = profile.get("personality_tags", [])
        if tags:
            profile_parts.append(f"性格特征: {', '.join(tags[:5])}")
        if profile_parts:
            parts.append("【用户画像】\n" + "\n".join(profile_parts))

        return "\n\n".join(parts)

    def _record_trace(
        self,
        prompt: str,
        response: str,
        started: float,
        error: str | None,
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
                agent_name="insight",
                call_type="generate",
                model=self._model,
                tier="heavy",
                prompt=prompt,
                response=response,
                latency_ms=(time.perf_counter() - started) * 1000,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                error=error,
            )
        )


__all__ = ["InsightAgent"]
