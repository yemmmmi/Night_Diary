"""Pure metric functions for episodic memory retrieval eval (V3 P5).

No I/O, no fixtures — just deterministic scoring of a ranked id list against a
set of gold ids. The three functions below are copied verbatim from
``tests/eval/rag/test_eval_retrieval.py`` so every retrieval eval reports the
same Recall@5 / MRR / nDCG@5 and stays in sync. Importing from another suite's
``test_*`` module would couple test files; a dedicated ``metrics.py`` mirrors
the convention already used by ``tool_call`` / ``skill_call`` / ``intent``.

Binary relevance, entry-id granularity (one gold set per query).
"""

from __future__ import annotations

import math

#: Cutoff for all three metrics; matches ``EpisodicMemory.retrieve_relevant`` default.
FINAL_K = 5

#: Ordered metric keys (used by baseline round-trip + report header).
METRIC_KEYS: tuple[str, ...] = ("recall@5", "mrr", "ndcg@5")


def recall_at_k(ranked: list[str], gold: set[str], k: int = FINAL_K) -> float:
    if not gold:
        return 0.0
    hits = sum(1 for entry_id in ranked[:k] if entry_id in gold)
    return hits / len(gold)


def reciprocal_rank(ranked: list[str], gold: set[str], k: int = FINAL_K) -> float:
    for index, entry_id in enumerate(ranked[:k]):
        if entry_id in gold:
            return 1.0 / (index + 1)
    return 0.0


def ndcg_at_k(ranked: list[str], gold: set[str], k: int = FINAL_K) -> float:
    if not gold:
        return 0.0
    dcg = sum(
        1.0 / math.log2(index + 2) for index, entry_id in enumerate(ranked[:k]) if entry_id in gold
    )
    ideal_hits = min(len(gold), k)
    idcg = sum(1.0 / math.log2(index + 2) for index in range(ideal_hits))
    return dcg / idcg if idcg > 0 else 0.0


__all__ = [
    "FINAL_K",
    "METRIC_KEYS",
    "recall_at_k",
    "reciprocal_rank",
    "ndcg_at_k",
]
