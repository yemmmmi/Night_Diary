"""两层对话意图分类器：规则层 + 可选的 LLM 层。

为对话（多轮对话）场景设计。遵循与
:class:`~app.domain.agents.intent_classifier.IntentClassifier` 相同的架构，
但使用对话专用的意图类别：

- ``casual_chat``: 闲聊，无需工具或检索
- ``emotional_vent``: 情绪宣泄，需情感支持
- ``retrospective_query``: 回溯查询，需 RAG 检索
- ``advice_seeking``: 求助建议，需检索 + 分析
- ``crisis_signal``: 危机信号，短路到安全响应
- ``entity_query``: 实体查询，需实体图查询

规则层先运行，在置信度足够时（> 0.9）直接短路，不消耗任何 token；
LLM 层仅在输入模糊时运行。
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from app.domain.agents.types import ChatIntent, ChatIntentResult
from app.shared.llm import LLMClient, message_text
from app.shared.tracing import LLMCallRecord, LLMCallTracer, NoOpLLMCallTracer

logger = logging.getLogger(__name__)

# ── 规则层关键词模式 ──────────────────────────────────────

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

#: 意图 → 路由表
_INTENT_ROUTING: dict[str, dict[str, Any]] = {
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
    """通过规则层然后可选 LLM 层对对话意图进行分类。

    镜像 :class:`IntentClassifier` 架构，但使用对话专用的类别和路由
    （层级、工具、最大迭代次数）。
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
        """返回 ``content`` 的对话意图。

        Args:
            content: 用户的消息文本。
            context: 用于消歧的简要压缩历史（可选）。
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
        """用于同步代码路径的 :meth:`classify` 同步变体。

        先使用规则层。如果需要 LLM，则通过 ``llm.invoke()`` 同步调用，
        而不是 ``await llm.ainvoke()``。
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
        """基于关键词的快速分类（零 token）。"""
        # 先检查危机信号——优先级最高
        for kw in _CRISIS_KEYWORDS:
            if kw in content:
                return self._build_result(ChatIntent.CRISIS_SIGNAL.value, 0.98)

        # 统计各类别的关键词命中数
        retrospective_hits = sum(1 for kw in _RETROSPECTIVE_KEYWORDS if kw in content)
        advice_hits = sum(1 for kw in _ADVICE_KEYWORDS if kw in content)
        emotional_hits = sum(1 for kw in _EMOTIONAL_VENT_KEYWORDS if kw in content)
        entity_hits = sum(1 for kw in _ENTITY_QUERY_KEYWORDS if kw in content)
        casual_hits = sum(1 for sig in _CASUAL_SIGNALS if sig in content.lower())

        is_short = len(content.strip()) < 20

        # 实体查询：提及某个人 + 询问其情况
        if entity_hits >= 2 and retrospective_hits == 0:
            return self._build_result(ChatIntent.ENTITY_QUERY.value, 0.85)
        if entity_hits >= 1 and any(kw in content for kw in ("怎么样", "怎么了", "最近")):
            return self._build_result(ChatIntent.ENTITY_QUERY.value, 0.80)

        # 回溯查询：时间关键词
        if retrospective_hits >= 2:
            if advice_hits >= 1:
                return self._build_result(ChatIntent.ADVICE_SEEKING.value, 0.90)
            return self._build_result(ChatIntent.RETROSPECTIVE_QUERY.value, 0.92)
        if retrospective_hits == 1 and advice_hits >= 1:
            return self._build_result(ChatIntent.ADVICE_SEEKING.value, 0.82)

        # 求助建议
        if advice_hits >= 2:
            return self._build_result(ChatIntent.ADVICE_SEEKING.value, 0.88)
        if advice_hits == 1 and not is_short:
            return self._build_result(ChatIntent.ADVICE_SEEKING.value, 0.75)

        # 情绪宣泄
        if emotional_hits >= 2:
            return self._build_result(ChatIntent.EMOTIONAL_VENT.value, 0.90)
        if emotional_hits == 1:
            return self._build_result(ChatIntent.EMOTIONAL_VENT.value, 0.75)

        # 闲聊
        if casual_hits >= 1 and is_short:
            return self._build_result(ChatIntent.CASUAL_CHAT.value, 0.92)
        if is_short and emotional_hits == 0 and advice_hits == 0:
            return self._build_result(ChatIntent.CASUAL_CHAT.value, 0.70)

        # 默认：中等置信度的闲聊
        return self._build_result(ChatIntent.CASUAL_CHAT.value, 0.50)

    @staticmethod
    def _build_result(category: str, confidence: float) -> ChatIntentResult:
        """根据路由表中的路由信息构建 ChatIntentResult。"""
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
        """针对模糊输入的基于 LLM 的分类。"""
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
        """解析 LLM 的 JSON 输出，失败时回退到规则提示。"""
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
