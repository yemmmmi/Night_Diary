"""ContextCompressor — 面向智能体管道的相关性排序历史压缩器。

从 V1 ``agents/context_compressor.py`` 迁移，并做了 V2 适配：

* Token 估算使用 :func:`~app.shared.token_utils.estimate_tokens`（单一
  事实来源——没有重复的估算器）。
* 语义相似度是**可注入的**；默认为
  :func:`~app.domain.agents.retrieval_agent.lexical_similarity`（jieba Jaccard），
  使得压缩器在运行时不需要嵌入模型。B-10+ 调用方可以在可用时注入一个
  语义评分器。
* 可选的 :class:`~app.shared.llm.LLMClient` 用于长条目摘要；当
  不可用或无法访问时，条目在句子边界处截断。
* 默认输出预算约为 1500 token——可放入工作记忆的 4000-token
  窗口中，与 Worker 输出并存。
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Mapping
from typing import Any

from app.domain.agents.retrieval_agent import lexical_similarity
from app.shared.llm import LLMClient, message_text
from app.shared.token_utils import estimate_tokens

logger = logging.getLogger(__name__)

DEFAULT_MAX_CONTEXT_TOKENS = 1500
MIN_CONTENT_LENGTH = 20
SUMMARIZE_THRESHOLD = 200

_GREETING_PATTERNS = re.compile(
    r"^(早安?|晚安?|你好|嗨|hi|hello|good\s*(morning|night|evening)|今天也要加油|"
    r"新的一天|打卡|签到|早上好|下午好|晚上好)[。！!.，,]?\s*$",
    re.IGNORECASE,
)

SimilarityFn = Callable[[str, str], float]


def is_low_density(content: str) -> bool:
    """当条目过短或仅为问候语时应返回 True（表示不值得保留）。"""
    if not content or len(content.strip()) < MIN_CONTENT_LENGTH:
        return True
    return bool(_GREETING_PATTERNS.match(content.strip()))


def _generate_summary(content: str, llm: LLMClient | None) -> str:
    """通过 LLM 摘要长条目，或在句子边界处截断。"""
    if llm is not None:
        try:
            prompt = f"请用一句话（不超过50字）概括以下日记内容的核心要点：\n\n{content[:500]}"
            response = llm.invoke(prompt)
            summary = message_text(response).strip()
            if summary and len(summary) < len(content):
                return summary
        except Exception as exc:
            logger.debug("context_compressor.summary_llm_failed: %s", exc)

    truncated = content[:180]
    for sep in ("。", "！", "？", "；", ".", "!", "?"):
        last_idx = truncated.rfind(sep)
        if last_idx > 80:
            return truncated[: last_idx + 1] + "..."
    return truncated + "..."


def _similarity_scores(
    query_text: str,
    candidates: list[dict[str, Any]],
    similarity: SimilarityFn,
) -> list[float]:
    if not candidates:
        return []
    return [similarity(query_text, c.get("content", "")) for c in candidates]


def _entry_content(entry: dict[str, Any]) -> str:
    """合并情景记忆的 ``event_summary`` + ``content``，使短标签也能携带信号。"""
    event = str(entry.get("event_summary") or "").strip()
    body = str(entry.get("content") or "").strip()
    if event and body and event != body:
        return f"{event}：{body}"
    return body or event


class ContextCompressor:
    """对历史进行排序、过滤、摘要，并贪婪地打包到 token 预算内。"""

    MAX_CONTEXT_TOKENS = DEFAULT_MAX_CONTEXT_TOKENS

    def __init__(
        self,
        *,
        max_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS,
        llm: LLMClient | None = None,
        similarity: SimilarityFn | None = None,
        episodic_boost: float = 0.2,
    ) -> None:
        self.max_tokens = max_tokens
        self._llm = llm
        self._similarity = similarity or lexical_similarity
        self._episodic_boost = episodic_boost

    def compress(
        self,
        current_content: str,
        *,
        candidates: list[dict[str, Any]] | None = None,
        episodic: list[dict[str, Any]] | None = None,
    ) -> str:
        """返回一个在 ``max_tokens`` 范围内、以 ``\\n---\\n`` 连接的上下文字符串。"""
        if not current_content.strip():
            return ""

        unified = self._unify_entries(episodic or [], candidates or [])
        if not unified:
            return ""

        filtered = [e for e in unified if not is_low_density(e["content"])]
        if not filtered:
            return ""

        scores = _similarity_scores(current_content, filtered, self._similarity)
        ranked = sorted(
            zip(scores, filtered, strict=True),
            key=lambda pair: pair[0] + pair[1]["priority_boost"],
            reverse=True,
        )

        parts: list[str] = []
        tokens_used = 0
        for _score, entry in ranked:
            content = entry["content"]
            if len(content) > SUMMARIZE_THRESHOLD:
                content = _generate_summary(content, self._llm)

            entry_tokens = estimate_tokens(content)
            if tokens_used + entry_tokens > self.max_tokens:
                remaining = self.max_tokens - tokens_used
                if remaining > 30:
                    max_chars = max(20, int(remaining / 1.5))
                    truncated = content[:max_chars].rstrip() + "..."
                    parts.append(truncated)
                break

            parts.append(content)
            tokens_used += entry_tokens

        return "\n---\n".join(parts)

    def _unify_entries(
        self,
        episodic: list[dict[str, Any]],
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        unified: list[dict[str, Any]] = []
        for entry in episodic:
            content = _entry_content(entry)
            if not content:
                continue
            unified.append(
                {
                    "content": content,
                    "source": "episodic",
                    "priority_boost": self._episodic_boost,
                }
            )
        for entry in candidates:
            content = str(entry.get("content") or "")
            if not content:
                continue
            unified.append(
                {
                    "content": content,
                    "source": "diary",
                    "priority_boost": 0.0,
                }
            )
        return unified


def prepare_compressed_history(
    state: Mapping[str, Any],
    compressor: ContextCompressor | None = None,
) -> dict[str, str]:
    """图准备步骤：将 ``episodic_context`` 压缩为 ``compressed_history``。"""
    episodic = state.get("episodic_context") or []
    if not episodic:
        return {}

    comp = compressor or ContextCompressor()
    compressed = comp.compress(
        state.get("diary_content", ""),
        episodic=episodic,
    )
    if not compressed:
        return {}
    return {"compressed_history": compressed}


def memory_context_from_state(state: Mapping[str, Any]) -> str:
    """优先使用 ``compressed_history``；回退到格式化原始情景记忆条目。"""
    compressed = state.get("compressed_history", "")
    if isinstance(compressed, str) and compressed.strip():
        return compressed.strip()

    episodic = state.get("episodic_context") or []
    lines: list[str] = []
    for entry in episodic[:5]:
        if not isinstance(entry, dict):
            continue
        parts: list[str] = []
        if entry.get("event_summary"):
            parts.append(f"事件：{entry['event_summary']}")
        if entry.get("emotion"):
            parts.append(f"情绪：{entry['emotion']}")
        if entry.get("content"):
            parts.append(str(entry["content"])[:120])
        if parts:
            lines.append("• " + "；".join(parts))
    return "\n".join(lines)


__all__ = [
    "DEFAULT_MAX_CONTEXT_TOKENS",
    "ContextCompressor",
    "is_low_density",
    "memory_context_from_state",
    "prepare_compressed_history",
]
