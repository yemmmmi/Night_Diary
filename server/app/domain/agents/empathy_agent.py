"""Empathy Worker 智能体——情感陪伴与危机安全响应。

从 V1 ``agents/empathy_agent.py`` 迁移。V2 变更：

* 所有依赖都是注入的：LLM（:class:`~app.shared.llm.LLMClient`）、
  共享的 :class:`~app.shared.emotion_estimator.EmotionEstimator`（不再
  重新实现关键词词表——那种重复是 V1 的坏味 3）、共享的
  :class:`~app.domain.knowledge.store.DomainKnowledgeStore`，以及
  :class:`~app.shared.tracing.LLMCallTracer`。
* 智能体内部没有 ``SessionLocal()`` / ``ChatOpenAI()`` / ``os.getenv``。
* ``run`` 是异步的（等待 ``ainvoke``），因此它加入 B-9 的并行扇出；
  ``fallback`` 是同步的，从不接触 LLM。
* PromptTuner *不* 在这里接入（B-9 关注点）；取而代之的是 ``run`` 接受一个
  可选的 ``style_fragment``，由 Supervisor 按请求传入。
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.domain.agents.context_compressor import memory_context_from_state
from app.domain.agents.prompts import (
    EMPATHY_BASE,
    EMPATHY_CRISIS_BLOCK,
    EMPATHY_CRISIS_FALLBACK,
    EMPATHY_FALLBACKS,
    EMPATHY_GUIDELINES,
    EMPATHY_RESPONSE_LENGTH,
    EMPATHY_STYLE_INSTRUCTIONS,
    normalize_style_key,
)
from app.domain.agents.state import MultiAgentState, extract_token_usage
from app.domain.knowledge.store import DomainKnowledgeStore
from app.domain.skills.crisis_detector import CRISIS_RESOURCES
from app.shared.emotion_estimator import EmotionEstimator, get_emotion_estimator
from app.shared.llm import LLMClient, message_text
from app.shared.tracing import LLMCallRecord, LLMCallTracer, NoOpLLMCallTracer

logger = logging.getLogger(__name__)

_DEFAULT_STYLE = "warm"
_DOMAIN_KNOWLEDGE_TOP_K = 2


class EmpathyAgent:
    """生成温暖、有情感感知的回复，并在危机信号时安全升级。"""

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
        self._emotion = emotion_estimator or get_emotion_estimator()
        self._tracer = tracer or NoOpLLMCallTracer()
        self._model = model

    async def run(
        self,
        state: MultiAgentState,
        *,
        style_fragment: str | None = None,
    ) -> dict[str, Any]:
        """为当前日记生成 ``empathy_response``（+ token 使用量）。"""
        diary_content = state.get("diary_content", "")
        intent = state.get("intent", "pure_record")
        profile = state.get("long_term_profile", {}) or {}

        is_crisis = self._is_crisis(diary_content, profile)
        preferred_style = str(profile.get("preferred_response_style", _DEFAULT_STYLE))

        domain_knowledge = ""
        if is_crisis or intent in ("emotional_support", "retrospective_review"):
            hits = self._knowledge.query(diary_content[:200], max_results=_DOMAIN_KNOWLEDGE_TOP_K)
            domain_knowledge = "\n".join(hit.content for hit in hits)

        system_prompt = self._build_system_prompt(
            intent=intent,
            preferred_style=preferred_style,
            episodic_context=memory_context_from_state(state),
            domain_knowledge=domain_knowledge,
            is_crisis=is_crisis,
            style_fragment=style_fragment,
        )

        # 用中性指令收尾, 不再硬编码「请给予温暖的回应」——
        # 那会把 pragmatic/calm 风格拉回 warm, 与上面的 style_fragment 打架。
        prompt = f"{system_prompt}\n\n日记内容：{diary_content}\n\n请回信。"

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
        """模型不可达时使用的安全、无 LLM 回复。"""
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
        style_fragment: str | None = None,
    ) -> str:
        length = EMPATHY_RESPONSE_LENGTH.get(intent, EMPATHY_RESPONSE_LENGTH["pure_record"])

        parts = [EMPATHY_BASE]
        # 有 per-request 风格覆盖时, 用 fragment 直接替代 profile 推导出的风格指令,
        # 避免两段风格文案同时出现在 prompt 里互相打架。
        if style_fragment:
            parts.append(f"\n{style_fragment}")
        else:
            style_desc = EMPATHY_STYLE_INSTRUCTIONS.get(
                normalize_style_key(preferred_style),
                EMPATHY_STYLE_INSTRUCTIONS["warm"],
            )
            parts.append(f"\n## 回应风格\n{style_desc}")
        parts.append(f"\n## 回应长度\n请将回应控制在 {length['min']}-{length['max']} 个汉字之间。")
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
