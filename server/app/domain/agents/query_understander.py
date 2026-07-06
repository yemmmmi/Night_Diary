"""QueryUnderstander — rewrites raw user input into a declarative retrieval query.

Sits between the IntentClassifier (which decides *whether* to retrieve) and
the RetrievalAgent (which executes the retrieval). Its job is:

1. **Coreference resolution**: replace pronouns ("那个", "上次说的") with
   explicit references from conversation context ("上周失眠", "项目延期").
2. **Declarative rewrite**: transform questions into declarative search
   queries ("我为什么总是失眠" → "失眠 反复 原因").
3. **Key term extraction**: identify the most discriminative terms for
   vector/BM25 retrieval.

Two layers (mirroring IntentClassifier):
- **Rule layer**: fast regex + keyword patterns for common coreference cases.
  Zero tokens, handles the 80% case.
- **LLM layer**: for ambiguous inputs where the rule layer has low confidence.
  Uses a light-tier LLM call with a compact prompt.

The LLM layer is optional — if no LLM is injected, only the rule layer runs
and the original query is returned unmodified when rules don't match.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass

from app.shared.llm import LLMClient, message_text
from app.shared.tracing import LLMCallRecord, LLMCallTracer, NoOpLLMCallTracer

logger = logging.getLogger(__name__)

# ── Rule layer patterns ──────────────────────────────────────────────

# Pronouns / deixis that need coreference resolution
_DEIXIS_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"那个(事情|事|时候|时间)"), "上次提到的事情"),
    (re.compile(r"上次(说的|提到的|写的)"), "之前记录的"),
    (re.compile(r"那(件|次)(事|经历)"), "之前的经历"),
    (re.compile(r"他(们)?(说|讲)的"), "之前提到的"),
    (re.compile(r"这个问题"), "这个问题"),
]

# Question → declarative rewrite patterns
_QUESTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"为什么(.+)"), r"\1 原因"),
    (re.compile(r"怎么(.+)"), r"\1 方法"),
    (re.compile(r"如何(.+)"), r"\1 方法"),
    (re.compile(r"(.+)怎么办"), r"\1 困扰"),
    (re.compile(r"(.+)怎么样了"), r"\1 现状"),
]

# Stop words for key term extraction
_STOP_WORDS = frozenset({
    "的", "了", "是", "在", "我", "你", "他", "她", "它",
    "这", "那", "和", "与", "或", "也", "都", "就", "还",
    "不", "没", "有", "要", "会", "能", "可以", "应该",
    "什么", "怎么", "为什么", "如何", "哪", "哪个", "哪些",
    "吗", "呢", "吧", "啊", "哦", "嗯",
})


@dataclass
class QueryUnderstanding:
    """Result of query understanding."""

    original: str
    rewritten: str
    key_terms: list[str]
    confidence: float
    used_llm: bool = False


QUERY_REWRITE_PROMPT = """你是一个查询理解助手。请将用户的输入改写为适合检索的声明式查询。

用户输入：{content}

对话上下文（最近几轮）：
{context}

请完成以下任务：
1. 共指消解：将代词（"那个"、"上次说的"）替换为上下文中的具体内容
2. 声明式改写：将疑问句改写为适合向量检索的声明式查询
3. 关键词提取：提取 3-5 个最具区分度的关键词

返回 JSON，格式如下：
{{"rewritten": "改写后的查询", "key_terms": ["关键词1", "关键词2"]}}

要求：
- 改写后的查询应保留用户的核心意图
- 关键词应避免停用词（的、了、是、我等）
- 用简洁的中文
"""


class QueryUnderstander:
    """Rewrite raw user input into a declarative retrieval query.

    Two-layer architecture:
    - Rule layer: fast regex patterns for common coreference/question cases.
    - LLM layer: optional, for ambiguous inputs.
    """

    RULE_CONFIDENCE_THRESHOLD = 0.7
    LLM_CONFIDENCE_THRESHOLD = 0.85

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

    def understand(
        self,
        content: str,
        *,
        context: str = "",
    ) -> QueryUnderstanding:
        """Understand and rewrite a user query.

        Args:
            content: Raw user input.
            context: Recent conversation history (for coreference resolution).

        Returns:
            QueryUnderstanding with rewritten query and key terms.
        """
        if not content or not content.strip():
            return QueryUnderstanding(
                original=content,
                rewritten=content,
                key_terms=[],
                confidence=1.0,
            )

        # ── Rule layer ──
        rewritten, rule_confidence = self._rule_rewrite(content, context)
        key_terms = self._extract_key_terms(rewritten)

        if rule_confidence >= self.RULE_CONFIDENCE_THRESHOLD:
            logger.debug(
                "query.rule_hit rewritten=%s confidence=%.2f terms=%s",
                rewritten,
                rule_confidence,
                key_terms,
            )
            return QueryUnderstanding(
                original=content,
                rewritten=rewritten,
                key_terms=key_terms,
                confidence=rule_confidence,
            )

        # ── LLM layer (optional) ──
        if self._llm is not None:
            try:
                result = self._llm_rewrite(content, context)
                if result.confidence >= self.LLM_CONFIDENCE_THRESHOLD:
                    return result
                # LLM result below threshold — merge with rule result
                merged = QueryUnderstanding(
                    original=content,
                    rewritten=result.rewritten if result.confidence > rule_confidence else rewritten,
                    key_terms=result.key_terms or key_terms,
                    confidence=max(result.confidence, rule_confidence),
                    used_llm=True,
                )
                return merged
            except Exception as exc:
                logger.warning("query.llm_failed, falling back to rule layer: %s", exc)

        return QueryUnderstanding(
            original=content,
            rewritten=rewritten,
            key_terms=key_terms,
            confidence=rule_confidence,
        )

    def _rule_rewrite(self, content: str, context: str) -> tuple[str, float]:
        """Apply rule-based coreference resolution and question rewrite.

        Returns (rewritten_query, confidence).
        """
        rewritten = content.strip()
        confidence = 0.5  # Base confidence — no rewrite applied

        # Coreference resolution via pattern matching
        for pattern, replacement in _DEIXIS_PATTERNS:
            if pattern.search(rewritten):
                rewritten = pattern.sub(replacement, rewritten)
                confidence = max(confidence, 0.75)

        # Question → declarative rewrite
        for pattern, replacement in _QUESTION_PATTERNS:
            match = pattern.search(rewritten)
            if match:
                rewritten = pattern.sub(replacement, rewritten, count=1)
                confidence = max(confidence, 0.80)
                break

        # If context is available and content starts with a deixis marker,
        # try to append context keywords
        if context and any(d in content for d in ("那个", "上次", "那件", "之前")):
            # Extract first sentence of context as disambiguation
            context_first = context.split("\n")[0][:30] if context else ""
            if context_first:
                rewritten = f"{rewritten} {context_first}"
                confidence = max(confidence, 0.70)

        return rewritten, confidence

    def _extract_key_terms(self, text: str) -> list[str]:
        """Extract discriminative key terms from text.

        Simple approach: split on punctuation, filter stop words, return
        top 5 by length (longer terms tend to be more discriminative in Chinese).
        """
        # Split on punctuation and whitespace
        parts = re.split(r"[，。！？；,\.!?\s\n]+", text.strip())
        terms = [
            p for p in parts
            if p and p not in _STOP_WORDS and len(p) >= 2
        ]
        # Deduplicate preserving order, take top 5
        seen: set[str] = set()
        unique: list[str] = []
        for t in terms:
            if t not in seen:
                seen.add(t)
                unique.append(t)
        return unique[:5]

    def _llm_rewrite(self, content: str, context: str) -> QueryUnderstanding:
        """Use LLM to rewrite the query with coreference resolution."""
        import asyncio

        prompt = QUERY_REWRITE_PROMPT.format(
            content=content[:500],
            context=context[:500] if context else "（无上下文）",
        )

        started = time.perf_counter()
        error: str | None = None
        text = ""
        try:
            # Use async invoke if available, otherwise sync
            if hasattr(self._llm, "ainvoke"):
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None

                if loop is not None and loop.is_running():
                    # We're in an async context — but understand() is sync.
                    # Fall back to sync invoke.
                    response = self._llm.invoke(prompt)
                else:
                    response = asyncio.run(self._llm.ainvoke(prompt))
            else:
                response = self._llm.invoke(prompt)
            text = message_text(response)
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            self._tracer.record(
                LLMCallRecord(
                    agent_name="query_understander",
                    call_type="rewrite",
                    model=self._model,
                    tier="light",
                    prompt=prompt,
                    response=text,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    error=error,
                )
            )

        # Parse JSON response
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            data = json.loads(cleaned)
            rewritten = str(data.get("rewritten", content))
            key_terms = list(data.get("key_terms", []))
            return QueryUnderstanding(
                original=content,
                rewritten=rewritten,
                key_terms=key_terms,
                confidence=0.90,
                used_llm=True,
            )
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            logger.warning("query.llm_parse_failed: %s | raw=%s", exc, text[:200])
            return QueryUnderstanding(
                original=content,
                rewritten=content,
                key_terms=self._extract_key_terms(content),
                confidence=0.5,
                used_llm=True,
            )


__all__ = ["QueryUnderstanding", "QueryUnderstander"]
