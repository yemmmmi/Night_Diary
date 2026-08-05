"""QueryUnderstander — 将原始用户输入改写为声明式检索查询。

位于 IntentClassifier（决定*是否*检索）和
RetrievalAgent（执行检索）之间。其职责是：

1. **共指消解**：将代词（"那个"、"上次说的"）替换为
   对话上下文中的明确引用（"上周失眠"、"项目延期"）。
2. **声明式改写**：将疑问句转换为声明式搜索
   查询（"我为什么总是失眠" → "失眠 反复 原因"）。
3. **关键词提取**：识别最具区分度的词项用于
   向量/BM25 检索。

两层架构（镜像 IntentClassifier）：
- **规则层**：快速正则 + 关键词模式，处理常见的共指情况。
  零 token，处理 80% 的情况。
- **LLM 层**：用于规则层置信度较低的模糊输入。
  使用 light 层级 LLM 调用，配以紧凑的提示词。

LLM 层是可选的——如果没有注入 LLM，则只运行规则层，
当规则不匹配时返回原始查询不做修改。
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

# ── 规则层模式 ──────────────────────────────────────────────

# 需要共指消解的代词/指示词
_DEIXIS_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"那个(事情|事|时候|时间)"), "上次提到的事情"),
    (re.compile(r"上次(说的|提到的|写的)"), "之前记录的"),
    (re.compile(r"那(件|次)(事|经历)"), "之前的经历"),
    (re.compile(r"他(们)?(说|讲)的"), "之前提到的"),
    (re.compile(r"这个问题"), "这个问题"),
]

# 疑问句 → 声明式改写模式
_QUESTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"为什么(.+)"), r"\1 原因"),
    (re.compile(r"怎么(.+)"), r"\1 方法"),
    (re.compile(r"如何(.+)"), r"\1 方法"),
    (re.compile(r"(.+)怎么办"), r"\1 困扰"),
    (re.compile(r"(.+)怎么样了"), r"\1 现状"),
]

# 关键词提取的停用词
_STOP_WORDS = frozenset(
    {
        "的",
        "了",
        "是",
        "在",
        "我",
        "你",
        "他",
        "她",
        "它",
        "这",
        "那",
        "和",
        "与",
        "或",
        "也",
        "都",
        "就",
        "还",
        "不",
        "没",
        "有",
        "要",
        "会",
        "能",
        "可以",
        "应该",
        "什么",
        "怎么",
        "为什么",
        "如何",
        "哪",
        "哪个",
        "哪些",
        "吗",
        "呢",
        "吧",
        "啊",
        "哦",
        "嗯",
    }
)


@dataclass
class QueryUnderstanding:
    """查询理解的结果。"""

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
    """将原始用户输入改写为声明式检索查询。

    两层架构：
    - 规则层：快速正则模式，处理常见的共指/疑问情况。
    - LLM 层：可选，用于模糊输入。
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
        """理解并改写用户查询。

        Args:
            content: 原始用户输入。
            context: 最近的对话历史（用于共指消解）。

        Returns:
            QueryUnderstanding，包含改写后的查询和关键词。
        """
        if not content or not content.strip():
            return QueryUnderstanding(
                original=content,
                rewritten=content,
                key_terms=[],
                confidence=1.0,
            )

        # ── 规则层 ──
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

        # ── LLM 层（可选）──
        if self._llm is not None:
            try:
                result = self._llm_rewrite(content, context)
                if result.confidence >= self.LLM_CONFIDENCE_THRESHOLD:
                    return result
                # LLM 结果低于阈值——与规则结果合并
                merged = QueryUnderstanding(
                    original=content,
                    rewritten=result.rewritten
                    if result.confidence > rule_confidence
                    else rewritten,
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
        """应用基于规则的共指消解和疑问改写。

        返回 (rewritten_query, confidence)。
        """
        rewritten = content.strip()
        confidence = 0.5  # 基础置信度——未应用改写

        # 通过模式匹配进行共指消解
        for pattern, replacement in _DEIXIS_PATTERNS:
            if pattern.search(rewritten):
                rewritten = pattern.sub(replacement, rewritten)
                confidence = max(confidence, 0.75)

        # 疑问句 → 声明式改写
        for pattern, replacement in _QUESTION_PATTERNS:
            match = pattern.search(rewritten)
            if match:
                rewritten = pattern.sub(replacement, rewritten, count=1)
                confidence = max(confidence, 0.80)
                break

        # 如果上下文可用且内容以指示词开头，
        # 尝试附加上下文关键词
        if context and any(d in content for d in ("那个", "上次", "那件", "之前")):
            # 提取上下文的第一句作为消歧信息
            context_first = context.split("\n")[0][:30] if context else ""
            if context_first:
                rewritten = f"{rewritten} {context_first}"
                confidence = max(confidence, 0.70)

        return rewritten, confidence

    def _extract_key_terms(self, text: str) -> list[str]:
        """从文本中提取有区分度的关键词。

        简单方法：按标点分割，过滤停用词，按长度返回
        前 5 个（在中文中，较长的词项往往更有区分度）。
        """
        # 按标点和空白分割
        parts = re.split(r"[，。！？；,\.!?\s\n]+", text.strip())
        terms = [p for p in parts if p and p not in _STOP_WORDS and len(p) >= 2]
        # 去重并保留顺序，取前 5 个
        seen: set[str] = set()
        unique: list[str] = []
        for t in terms:
            if t not in seen:
                seen.add(t)
                unique.append(t)
        return unique[:5]

    def _llm_rewrite(self, content: str, context: str) -> QueryUnderstanding:
        """使用 LLM 改写查询并进行共指消解。"""
        import asyncio

        prompt = QUERY_REWRITE_PROMPT.format(
            content=content[:500],
            context=context[:500] if context else "（无上下文）",
        )

        started = time.perf_counter()
        error: str | None = None
        text = ""
        try:
            llm = self._llm
            if llm is None:
                return QueryUnderstanding(
                    original=content,
                    rewritten=content,
                    key_terms=[],
                    confidence=0.0,
                    used_llm=False,
                )
            # 如果可用则使用异步调用，否则同步调用
            if hasattr(llm, "ainvoke"):
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None

                if loop is not None and loop.is_running():
                    # 我们在异步上下文中——但 understand() 是同步的。
                    # 回退到同步调用。
                    response = llm.invoke(prompt)
                else:
                    response = asyncio.run(llm.ainvoke(prompt))
            else:
                response = llm.invoke(prompt)
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

        # 解析 JSON 响应
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


__all__ = ["QueryUnderstander", "QueryUnderstanding"]
