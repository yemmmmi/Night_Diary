"""两层意图分类器：规则层 + 可选的 LLM 层。

从 V1 ``agents/intent_classifier.py`` 迁移。V2 变更：

* LLM 作为 :class:`~app.shared.llm.LLMClient` 注入（没有模块级
  ``ChatOpenAI``）；LLM 层级通过 ``ainvoke`` 等待，使分类器适配
  异步管道。
* 每次 LLM 调用通过注入的
  :class:`~app.shared.tracing.LLMCallTracer` 记录（call_type ``classify``，tier
  ``light``）——分类是最便宜的 LLM 跳转，仍必须可观测。
* 规则层先运行，在置信度足够时（> 0.9）直接短路，不消耗任何 token；
  LLM 层仅在输入模糊时运行，任何 LLM 失败都降级到规则层结果。
"""

from __future__ import annotations

import json
import logging
import re
import time

from app.domain.agents.prompts import INTENT_CLASSIFY_PROMPT
from app.domain.agents.types import IntentCategory, IntentResult
from app.shared.llm import LLMClient, message_text
from app.shared.tracing import LLMCallRecord, LLMCallTracer, NoOpLLMCallTracer

logger = logging.getLogger(__name__)

_TEMPORAL_STRONG = (
    "昨天",
    "前天",
    "上周",
    "上个月",
    "去年",
    "前几天",
    "前段时间",
    "那天",
    "那时",
    "那次",
    "上次",
    "曾经",
)
_TEMPORAL_MEDIUM = (
    "又",
    "还是",
    "老是",
    "总是",
    "每次",
    "再次",
    "重复",
    "一直",
    "和之前一样",
    "跟上次",
    "像上回",
)
_TEMPORAL_PHRASES = (
    "之前写过",
    "以前提到",
    "上次说",
    "之前也是",
    "和前几天一样",
    "跟上次一样",
    "像上回一样",
)
_WEATHER_KEYWORDS = (
    "天气",
    "气温",
    "下雨",
    "下雪",
    "阴天",
    "晴天",
    "大风",
    "闷热",
    "寒冷",
    "潮湿",
    "雾霾",
    "温度",
)
_STRONG_EMOTION_PATTERNS = (
    "崩溃",
    "绝望",
    "痛苦",
    "焦虑",
    "抑郁",
    "失眠",
    "不想活",
    "没意思",
    "受不了",
    "快疯了",
    "撑不住",
    "太难了",
    "好累",
    "心碎",
    "无助",
    "恐惧",
)
_ANALYSIS_KEYWORDS = (
    "为什么",
    "怎么办",
    "该怎样",
    "如何改变",
    "规律",
    "总结",
    "回顾",
    "反思",
    "复盘",
    "模式",
    "习惯",
    "进步",
    "目标",
    "计划",
)
_PURE_RECORD_SIGNALS = (
    "今天吃了",
    "今天去了",
    "今天看了",
    "今天做了",
    "记录一下",
    "流水账",
    "日常",
)


class IntentClassifier:
    """通过快速规则层然后可选 LLM 层对日记意图进行分类。"""

    CONFIDENCE_THRESHOLD = 0.9

    def __init__(
        self,
        llm: LLMClient | None = None,
        *,
        tracer: LLMCallTracer | None = None,
        model: str = "",
    ) -> None:
        self._llm = llm
        self._tracer = tracer or NoOpLLMCallTracer()
        self._model = model

    async def classify(self, content: str) -> IntentResult:
        """返回 ``content`` 的意图（规则层优先，模糊时用 LLM）。"""
        if not content or not content.strip():
            return IntentResult(
                intent_category=IntentCategory.PURE_RECORD.value,
                confidence=1.0,
            )

        rule_result = self._rule_classify(content)
        if rule_result.confidence > self.CONFIDENCE_THRESHOLD:
            logger.debug(
                "intent.rule_hit category=%s confidence=%.2f",
                rule_result.intent_category,
                rule_result.confidence,
            )
            return rule_result

        if self._llm is not None:
            try:
                return await self._llm_classify(content, rule_result)
            except Exception as exc:
                logger.warning("intent.llm_failed, falling back to rule layer: %s", exc)
                return rule_result

        return rule_result

    def _rule_classify(self, content: str) -> IntentResult:
        retrieval_score = 0.0
        weather_score = 0.0
        analysis_score = 0.0

        for phrase in _TEMPORAL_PHRASES:
            if phrase in content:
                retrieval_score = max(retrieval_score, 0.95)
                break

        strong_temporal = sum(1 for kw in _TEMPORAL_STRONG if kw in content)
        if strong_temporal >= 2:
            retrieval_score = max(retrieval_score, 0.95)
        elif strong_temporal == 1:
            retrieval_score = max(retrieval_score, 0.85)

        medium_temporal = sum(1 for kw in _TEMPORAL_MEDIUM if kw in content)
        if medium_temporal >= 2:
            retrieval_score = max(retrieval_score, 0.80)
        elif medium_temporal == 1:
            retrieval_score = max(retrieval_score, 0.60)

        weather_count = sum(1 for kw in _WEATHER_KEYWORDS if kw in content)
        if weather_count >= 2:
            weather_score = 0.95
        elif weather_count == 1:
            weather_score = 0.75

        emotion_count = sum(1 for kw in _STRONG_EMOTION_PATTERNS if kw in content)
        analysis_kw_count = sum(1 for kw in _ANALYSIS_KEYWORDS if kw in content)
        if emotion_count >= 2:
            analysis_score = max(analysis_score, 0.95)
        elif emotion_count == 1:
            analysis_score = max(analysis_score, 0.80)
        if analysis_kw_count >= 2:
            analysis_score = max(analysis_score, 0.92)
        elif analysis_kw_count == 1:
            analysis_score = max(analysis_score, 0.70)

        pure_record_count = sum(1 for sig in _PURE_RECORD_SIGNALS if sig in content)
        is_short = len(content.strip()) < 50
        pure_record_score = 0.0
        if pure_record_count >= 1 and is_short:
            pure_record_score = 0.95
        elif pure_record_count >= 1:
            pure_record_score = 0.80
        elif is_short and retrieval_score < 0.5 and analysis_score < 0.5:
            pure_record_score = 0.75

        need_retrieval = retrieval_score >= 0.75
        need_weather = weather_score >= 0.75
        need_analysis = analysis_score >= 0.75

        category, confidence = self._resolve_category(
            retrieval_score=retrieval_score,
            analysis_score=analysis_score,
            pure_record_score=pure_record_score,
        )

        return IntentResult(
            intent_category=category,
            need_retrieval=need_retrieval,
            need_weather=need_weather,
            need_analysis=need_analysis,
            confidence=confidence,
        )

    @staticmethod
    def _resolve_category(
        *,
        retrieval_score: float,
        analysis_score: float,
        pure_record_score: float,
    ) -> tuple[str, float]:
        if pure_record_score >= 0.9 and retrieval_score < 0.75 and analysis_score < 0.75:
            return IntentCategory.PURE_RECORD.value, pure_record_score
        if retrieval_score >= 0.75 and analysis_score >= 0.75:
            return (
                IntentCategory.RETROSPECTIVE_REVIEW.value,
                (retrieval_score + analysis_score) / 2
                if not (retrieval_score >= 0.9 and analysis_score >= 0.9)
                else min(retrieval_score, analysis_score),
            )
        if retrieval_score >= 0.75:
            return IntentCategory.RETROSPECTIVE_REVIEW.value, retrieval_score
        if analysis_score >= 0.75:
            return IntentCategory.EMOTIONAL_SUPPORT.value, analysis_score
        return IntentCategory.PURE_RECORD.value, max(pure_record_score, 0.5)

    async def _llm_classify(self, content: str, rule_hint: IntentResult) -> IntentResult:
        prompt = INTENT_CLASSIFY_PROMPT.format(content=content[:500])

        started = time.perf_counter()
        error: str | None = None
        text = ""
        try:
            response = await self._llm.ainvoke(prompt)  # type: ignore[union-attr]
            text = message_text(response)
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            self._tracer.record(
                LLMCallRecord(
                    agent_name="intent_classifier",
                    call_type="classify",
                    model=self._model,
                    tier="light",
                    prompt=prompt,
                    response=text,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    error=error,
                )
            )

        return self._parse_llm_output(text, rule_hint)

    @staticmethod
    def _parse_llm_output(text: str, rule_hint: IntentResult) -> IntentResult:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            data = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            logger.warning("intent.llm_parse_failed: %s | raw=%s", exc, text[:200])
            return IntentResult(
                intent_category=rule_hint.intent_category,
                need_retrieval=rule_hint.need_retrieval,
                need_weather=rule_hint.need_weather,
                need_analysis=rule_hint.need_analysis,
                confidence=max(rule_hint.confidence, 0.6),
            )

        return IntentResult(
            intent_category=str(data.get("intent_category", rule_hint.intent_category)),
            need_retrieval=bool(data.get("need_retrieval", rule_hint.need_retrieval)),
            need_weather=bool(data.get("need_weather", rule_hint.need_weather)),
            need_analysis=bool(data.get("need_analysis", rule_hint.need_analysis)),
            confidence=min(1.0, max(0.0, float(data.get("confidence", 0.7)))),
        )


__all__ = ["IntentClassifier"]
