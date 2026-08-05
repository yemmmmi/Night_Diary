"""Retrieval Worker Agent — RAG-augmented context over the user's own diaries.

Migrated from V1 ``agents/retrieval_agent.py`` and re-scoped for V2 (Q4 = minimal):

* Retrieval goes through the injected B-3 :class:`~app.domain.rag.retriever.HybridRetriever`
  (Chroma + BM25 + RRF + optional rerank) and the shared
  :class:`~app.domain.knowledge.store.DomainKnowledgeStore`. No agent-local
  ChromaDB clients.
* V1's structured ``KnowledgeEntry`` SQL branch is **dropped** — that table does
  not exist in V2 and is out of B-8 scope.
* Multi-hop retrieval (≤ 3 hops) with an *anchor* guard: each refined query must
  stay lexically close to the original query (similarity ≥ ``anchor_threshold``),
  otherwise the hop loop stops to prevent query drift. The similarity function is
  injectable; the default is a jieba token-overlap (Jaccard) heuristic so the
  anchor needs no embedding model at runtime (B-10 can inject a semantic one).
* ``time_range`` is accepted but reserved: ``HybridRetriever.retrieve`` has no
  date filter yet, and client-side post-filtering cannot improve recall, so B-8
  leaves it ``None``. The parameter is declared now so the signature is stable.
* No LLM call here, hence no ``LLMCallTracer`` — this agent only retrieves and
  summarises. ``run`` is async purely for a uniform Worker interface.
"""

from __future__ import annotations

import logging
from typing import Any

import jieba

from app.domain.agents.state import MultiAgentState
from app.domain.knowledge.store import DomainKnowledgeStore
from app.domain.rag.retriever import HybridRetriever
from app.domain.rag.types import RetrievalResult
from app.shared.token_utils import estimate_tokens

logger = logging.getLogger(__name__)

_DEFAULT_MAX_HOPS = 3
_DEFAULT_ANCHOR_THRESHOLD = 0.3
_DEFAULT_RELEVANCE_THRESHOLD = 0.3
_DEFAULT_TOP_K = 5
_MAX_SUMMARY_TOKENS = 300
_DOMAIN_KNOWLEDGE_TOP_K = 2


def lexical_similarity(left: str, right: str) -> float:
    """Jaccard overlap of jieba tokens — a cheap, model-free query similarity."""
    left_tokens = {t for t in jieba.cut(left) if t.strip()}
    right_tokens = {t for t in jieba.cut(right) if t.strip()}
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = left_tokens & right_tokens
    union = left_tokens | right_tokens
    return len(intersection) / len(union)


class RetrievalAgent:
    """Retrieve relevant past diaries + domain knowledge into a compact summary."""

    def __init__(
        self,
        retriever: HybridRetriever,
        knowledge: DomainKnowledgeStore,
        *,
        query_similarity: Any | None = None,
        max_hops: int = _DEFAULT_MAX_HOPS,
        anchor_threshold: float = _DEFAULT_ANCHOR_THRESHOLD,
        relevance_threshold: float = _DEFAULT_RELEVANCE_THRESHOLD,
        top_k: int = _DEFAULT_TOP_K,
        max_summary_tokens: int = _MAX_SUMMARY_TOKENS,
    ) -> None:
        self._retriever = retriever
        self._knowledge = knowledge
        self._similarity = query_similarity or lexical_similarity
        self._max_hops = max_hops
        self._anchor_threshold = anchor_threshold
        self._relevance_threshold = relevance_threshold
        self._top_k = top_k
        self._max_summary_tokens = max_summary_tokens

    async def run(
        self,
        state: MultiAgentState,
        *,
        time_range: tuple[str, str] | None = None,
    ) -> dict[str, Any]:
        """Produce ``retrieval_context`` — a ≤300-token summary of relevant history."""
        _ = time_range  # reserved; HybridRetriever has no date filter yet (see module docstring)
        diary_content = state.get("diary_content", "")
        if not diary_content.strip():
            return {"retrieval_context": ""}

        results = self._multi_hop_retrieve(diary_content)
        domain_knowledge = [
            hit.content
            for hit in self._knowledge.query(
                diary_content[:200], max_results=_DOMAIN_KNOWLEDGE_TOP_K
            )
        ]
        summary = self._build_summary(results, domain_knowledge)

        logger.info(
            "retrieval.done results=%d domain=%d summary_len=%d",
            len(results),
            len(domain_knowledge),
            len(summary),
        )
        return {"retrieval_context": summary}

    def fallback(self) -> dict[str, Any]:
        """Safe degraded result: an empty context marker (no retrieval)."""
        return {"retrieval_context": ""}

    def _multi_hop_retrieve(self, query: str) -> list[RetrievalResult]:
        collected: list[RetrievalResult] = []
        seen: set[str] = set()
        current_query = query

        for hop in range(self._max_hops):
            try:
                hits = self._retriever.retrieve(current_query, top_k=self._top_k)
            except Exception as exc:
                logger.warning("retrieval.hop_failed hop=%d: %s", hop + 1, exc)
                break

            new_hits = [h for h in hits if (h.diary_id or h.doc_id) not in seen]
            for hit in new_hits:
                seen.add(hit.diary_id or hit.doc_id)
            collected.extend(new_hits)

            relevance = self._assess_relevance(collected)
            logger.debug(
                "retrieval.hop hop=%d new=%d total=%d relevance=%.3f",
                hop + 1,
                len(new_hits),
                len(collected),
                relevance,
            )

            if relevance >= self._relevance_threshold and len(collected) >= 2:
                break
            if not new_hits and hop > 0:
                break

            refined = self._refine_query(query, new_hits)
            # Anchor guard: stop if the refined query has drifted from the original.
            if self._similarity(query, refined) < self._anchor_threshold:
                logger.debug("retrieval.anchor_stop hop=%d (query drift)", hop + 1)
                break
            current_query = refined

        return collected[: self._top_k]

    @staticmethod
    def _assess_relevance(results: list[RetrievalResult]) -> float:
        if not results:
            return 0.0
        scores = [max(0.0, min(1.0, r.rerank_score or r.score or 0.0)) for r in results]
        return sum(scores) / len(scores)

    @staticmethod
    def _refine_query(original_query: str, previous_hits: list[RetrievalResult]) -> str:
        if not previous_hits:
            return original_query
        snippet = previous_hits[0].content[:50]
        return f"{original_query} {snippet}".strip()[:200]

    def _build_summary(
        self,
        results: list[RetrievalResult],
        domain_knowledge: list[str],
    ) -> str:
        parts: list[str] = []
        tokens_used = 0

        if results:
            diary_lines: list[str] = []
            for item in results:
                content = item.content[:100] + "..." if len(item.content) > 100 else item.content
                line = f"[{item.date}] {content}" if item.date else content
                line_tokens = estimate_tokens(line)
                if tokens_used + line_tokens > self._max_summary_tokens * 0.7:
                    break
                diary_lines.append(line)
                tokens_used += line_tokens
            if diary_lines:
                parts.append("【相关日记】\n" + "\n".join(diary_lines))

        if domain_knowledge:
            domain_lines: list[str] = []
            for entry in domain_knowledge[:_DOMAIN_KNOWLEDGE_TOP_K]:
                text = entry[:80] + "..." if len(entry) > 80 else entry
                entry_tokens = estimate_tokens(text)
                if tokens_used + entry_tokens > self._max_summary_tokens:
                    break
                domain_lines.append(text)
                tokens_used += entry_tokens
            if domain_lines:
                parts.append("【领域参考】\n" + "\n".join(domain_lines))

        return "\n\n".join(parts)


__all__ = ["RetrievalAgent", "lexical_similarity"]
