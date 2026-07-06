"""Two-tier chat intent classifier: rule layer + optional LLM layer.

Designed for the conversation (multi-turn dialogue) scenario. Follows the
same architecture as :class:`~app.domain.agents.intent_classifier.IntentClassifier`
but with chat-specific intent categories:

- ``casual_chat``: 闲聊，无需工具或检索
- ``emotional_vent``: 情绪宣泄，需情感支持
- ``retrospective_query``: 回溯查询，需 RAG 检索
- ``advice_seeking``: 求助建议，需检索 + 分析
- ``crisis_signal``: 危机信号，短路到安全响应
- ``entity_query``: 实体查询，需实体图查询

The rule layer runs first and short-circuits when confident (> 0.9),
spending zero tokens; the LLM layer only runs on ambiguous input.
"""

from __future__ import annotations

import json
import logging
import re
import time

from app.domain.agents.types import ChatIntent, ChatIntentResult
from app.shared.llm import LLMClient, message_text
from app.shared.tracing import LLMCallRecord, LLMCallTracer, NoOpLLMCallTracer

logger = logging.getLogger(__name__)

# ── Rule layer keyword patterns ──────────────────────────────────────

_CRISIS_KEYWORDS = (
    "不想活",
    "自杀",
    "结束生命",
    "活不下去",
    "想死",
    "杀了",
    "伤害自己",
    "了结",
    "跳楼",
    "吃药结束",
)

_RETROSPECTIVE_KEYWORDS = (
    "上次",
    "之前",
    "那天",
    "那次",
    "以前",
    "记得吗",
    "说过",
    "提到过",
    "聊过",
    "昨天",
    "前天",
    "上周",
    "上个月",
)

_ADVICE_KEYWORDS = (
    "怎么办",
    "该怎么",
    "如何",
    "建议",
    "意见",
    "帮我",
    "能不能",
    "有什么方法",
    "怎样能",
    "为什么",
    "原因",
    "解决",
)

_EMOTIONAL_VENT_KEYWORDS = (
    "崩溃",
    "绝望",
    "痛苦",
    "焦虑",
    "抑郁",
    "失眠",
    "受不了",
    "快疯了",
    "撑不住",
    "太难了",
    "好累",
    "心碎",
    "无助",
    "恐惧",
    "烦死了",
    "气死",
    "委屈",
    "难过",
    "孤独",
)

_ENTITY_QUERY_KEYWORDS = (
    "妈妈",
    "爸爸",
    "老公",
    "老婆",
    "男友",
    "女友",
    "儿子",
    "女儿",
    "老板",
    "同事",
    "老师",
    "朋友",
    "最近怎么样",
    "怎么了",
    "在干嘛",
)

_CASUAL_SIGNALS = (
    "早安",
    "晚安",
    "你好",
    "嗨",
    "hi",
    "hello",
    "谢谢",
    "好的",
    "嗯嗯",
    "哈哈",
    "哦",
)

#: Intent → routing table
_INTENT_ROUTING = {
    ChatIntent.CASUAL_CHAT.value: {
        "need_retrieval": False,
        "need_tools": [],
        "need_entity_query": False,
        "tier": "light",
        "max_iterations": 1,
    },
    ChatIntent.EMOTIONAL_VENT.value: {
        "need_retrieval": False,
        "need_tools": ["analyze_sentiment"],
        "need_entity_query": False,
        "tier": "medium",
        "max_iterations": 1,
    },
    ChatIntent.RETROSPECTIVE_QUERY.value: {
        "need_retrieval": True,
        "need_tools": ["search_diary"],
        "need_entity_query": False,
        "tier": "heavy",
        "max_iterations": 3,
    },
    ChatIntent.ADVICE_SEEKING.value: {
        "need_retrieval": True,
        "need_tools": ["search_diary", "analyze_sentiment"],
        "need_entity_query": False,
        "tier": "heavy",
        "max_iterations": 3,
    },
    ChatIntent.CRISIS_SIGNAL.value: {
        "need_retrieval": False,
        "need_tools": [],
        "need_entity_query": False,
        "tier": "crisis",
        "max_iterations": 1,
    },
    ChatIntent.ENTITY_QUERY.value: {
        "need_retrieval": False,
        "need_tools": ["query_entity_graph"],
        "need_entity_query": True,
        "tier": "medium",
        "max_iterations": 2,
    },
}

_CHAT_INTENT_PROMPT = """请分析以下用户消息的意图，返回JSON格式。

用户消息：{content}

意图类别（选择最匹配的一个）：
- casual_chat: 闲聊、问候、简短回应
- emotional_vent: 情绪宣泄、表达负面情绪
- retrospective_query: 回溯过去的事情、询问之前的记录
- advice_seeking: 寻求建议、询问方法或解决方案
- crisis_signal: 表达自伤/自杀意念或极度绝望
- entity_query: 询问特定人物或事物的近况

返回JSON：
```json
{{
  "intent_category": "casual_chat",
  "confidence": 0.9,
  "need_retrieval": false,
  "need_tools": [],
  "need_entity_query": false
}}
```"""


class ChatIntentClassifier:
    """Classify conversation intent via rule layer then optional LLM layer.

    Mirrors :class:`IntentClassifier` architecture but with chat-specific
    categories and routing (tier, tools, max_iterations).
    """

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

    async def classify(self, content: str, *, context: str = "") -> ChatIntentResult:
        """Return the chat intent for ``content``.

        Args:
            content: The user's message text.
            context: Brief compressed history for disambiguation (optional).
        """
        if not content or not content.strip():
            return ChatIntentResult(
                intent_category=ChatIntent.CASUAL_CHAT.value,
                confidence=1.0,
            )

        rule_result = self._rule_classify(content)
        if rule_result.confidence > self.CONFIDENCE_THRESHOLD:
            logger.debug(
                "chat_intent.rule_hit category=%s confidence=%.2f",
                rule_result.intent_category,
                rule_result.confidence,
            )
            return rule_result

        if self._llm is not None:
            try:
                return await self._llm_classify(content, rule_result)
            except Exception as exc:
                logger.warning("chat_intent.llm_failed, falling back to rule layer: %s", exc)
                return rule_result

        return rule_result

    def classify_sync(self, content: str, *, context: str = "") -> ChatIntentResult:
        """Synchronous variant of :meth:`classify` for sync code paths.

        Uses the rule layer first. If LLM is needed, invokes synchronously
        via ``llm.invoke()`` instead of ``await llm.ainvoke()``.
        """
        if not content or not content.strip():
            return ChatIntentResult(
                intent_category=ChatIntent.CASUAL_CHAT.value,
                confidence=1.0,
            )

        rule_result = self._rule_classify(content)
        if rule_result.confidence > self.CONFIDENCE_THRESHOLD:
            return rule_result

        if self._llm is not None:
            try:
                prompt = _CHAT_INTENT_PROMPT.format(content=content[:500])
                started = time.perf_counter()
                response = self._llm.invoke(prompt)
                text = message_text(response)
                self._tracer.record(
                    LLMCallRecord(
                        agent_name="chat_intent_classifier",
                        call_type="classify",
                        model=self._model,
                        tier="light",
                        prompt=prompt,
                        response=text,
                        latency_ms=(time.perf_counter() - started) * 1000,
                    )
                )
                return self._parse_llm_output(text, rule_result)
            except Exception as exc:
                logger.warning("chat_intent.llm_sync_failed, falling back to rule layer: %s", exc)
                return rule_result

        return rule_result

    def _rule_classify(self, content: str) -> ChatIntentResult:
        """Fast keyword-based classification (zero tokens)."""
        # Crisis check first — highest priority
        for kw in _CRISIS_KEYWORDS:
            if kw in content:
                return self._build_result(ChatIntent.CRISIS_SIGNAL.value, 0.98)

        # Count keyword hits per category
        retrospective_hits = sum(1 for kw in _RETROSPECTIVE_KEYWORDS if kw in content)
        advice_hits = sum(1 for kw in _ADVICE_KEYWORDS if kw in content)
        emotional_hits = sum(1 for kw in _EMOTIONAL_VENT_KEYWORDS if kw in content)
        entity_hits = sum(1 for kw in _ENTITY_QUERY_KEYWORDS if kw in content)
        casual_hits = sum(1 for sig in _CASUAL_SIGNALS if sig in content.lower())

        is_short = len(content.strip()) < 20

        # Entity query: mentions a person + asks about them
        if entity_hits >= 2 and retrospective_hits == 0:
            return self._build_result(ChatIntent.ENTITY_QUERY.value, 0.85)
        if entity_hits >= 1 and any(kw in content for kw in ("怎么样", "怎么了", "最近")):
            return self._build_result(ChatIntent.ENTITY_QUERY.value, 0.80)

        # Retrospective query: temporal keywords
        if retrospective_hits >= 2:
            if advice_hits >= 1:
                return self._build_result(ChatIntent.ADVICE_SEEKING.value, 0.90)
            return self._build_result(ChatIntent.RETROSPECTIVE_QUERY.value, 0.92)
        if retrospective_hits == 1 and advice_hits >= 1:
            return self._build_result(ChatIntent.ADVICE_SEEKING.value, 0.82)

        # Advice seeking
        if advice_hits >= 2:
            return self._build_result(ChatIntent.ADVICE_SEEKING.value, 0.88)
        if advice_hits == 1 and not is_short:
            return self._build_result(ChatIntent.ADVICE_SEEKING.value, 0.75)

        # Emotional vent
        if emotional_hits >= 2:
            return self._build_result(ChatIntent.EMOTIONAL_VENT.value, 0.90)
        if emotional_hits == 1:
            return self._build_result(ChatIntent.EMOTIONAL_VENT.value, 0.75)

        # Casual chat
        if casual_hits >= 1 and is_short:
            return self._build_result(ChatIntent.CASUAL_CHAT.value, 0.92)
        if is_short and emotional_hits == 0 and advice_hits == 0:
            return self._build_result(ChatIntent.CASUAL_CHAT.value, 0.70)

        # Default: medium confidence casual chat
        return self._build_result(ChatIntent.CASUAL_CHAT.value, 0.50)

    @staticmethod
    def _build_result(category: str, confidence: float) -> ChatIntentResult:
        """Build a ChatIntentResult with routing info from the routing table."""
        routing = _INTENT_ROUTING.get(category, _INTENT_ROUTING[ChatIntent.CASUAL_CHAT.value])
        return ChatIntentResult(
            intent_category=category,
            need_retrieval=routing["need_retrieval"],
            need_tools=list(routing["need_tools"]),
            need_entity_query=routing["need_entity_query"],
            tier=routing["tier"],
            max_iterations=routing["max_iterations"],
            confidence=confidence,
        )

    async def _llm_classify(self, content: str, rule_hint: ChatIntentResult) -> ChatIntentResult:
        """LLM-based classification for ambiguous input."""
        prompt = _CHAT_INTENT_PROMPT.format(content=content[:500])

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
                    agent_name="chat_intent_classifier",
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
    def _parse_llm_output(text: str, rule_hint: ChatIntentResult) -> ChatIntentResult:
        """Parse LLM JSON output, falling back to rule hint on failure."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            data = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            logger.warning("chat_intent.llm_parse_failed: %s | raw=%s", exc, text[:200])
            return ChatIntentResult(
                intent_category=rule_hint.intent_category,
                need_retrieval=rule_hint.need_retrieval,
                need_tools=rule_hint.need_tools,
                need_entity_query=rule_hint.need_entity_query,
                tier=rule_hint.tier,
                max_iterations=rule_hint.max_iterations,
                confidence=max(rule_hint.confidence, 0.6),
            )

        category = str(data.get("intent_category", rule_hint.intent_category))
        routing = ChatIntentClassifier._build_result(category, 0.8)

        return ChatIntentResult(
            intent_category=category,
            need_retrieval=bool(data.get("need_retrieval", routing.need_retrieval)),
            need_tools=list(data.get("need_tools", routing.need_tools)),
            need_entity_query=bool(data.get("need_entity_query", routing.need_entity_query)),
            tier=routing.tier,
            max_iterations=routing.max_iterations,
            confidence=min(1.0, max(0.0, float(data.get("confidence", 0.75)))),
        )


__all__ = ["ChatIntentClassifier"]
