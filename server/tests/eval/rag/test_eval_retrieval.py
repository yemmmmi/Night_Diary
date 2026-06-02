"""Offline RAG retrieval baseline: BM25 / vector / hybrid-RRF / hybrid+rerank.

Runs every branch through the *production* :class:`HybridRetriever` by varying
which sub-retriever carries data, computes Recall@5 / MRR / nDCG@5 over the
fixed corpus, prints a comparison table plus failure samples, and guards against
per-branch regression versus a recorded ``baseline.json``.

Run it manually (out of CI):

    make eval-rag                       # report + regression check
    EVAL_UPDATE_BASELINE=1 make eval-rag  # (re)seed baseline.json

See ``BASELINE.md`` for model versions, prefix policy and recorded values.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

import pytest

from app.domain.rag.bm25 import BM25Index
from app.domain.rag.collections import DiaryCollectionManager
from app.domain.rag.reranker import Reranker
from app.domain.rag.retriever import HybridRetriever

# Excluded from the default test run (CI); selected only via `make eval-rag`.
pytestmark = pytest.mark.eval

FINAL_K = 5
# Absolute tolerance: small-sample fluctuation is allowed; a drop beyond this
# below the recorded baseline is treated as a real regression to explain/fix.
REGRESSION_TOLERANCE = 0.05
BASELINE_PATH = Path(__file__).parent / "baseline.json"
METRIC_KEYS = ("recall@5", "mrr", "ndcg@5")


class _EmptyCollections:
    """Collection stub whose vector branch returns nothing (BM25-only runs)."""

    def get_collection(self, *, create: bool = False) -> None:
        return None


# --------------------------------------------------------------------------- #
# Metrics (binary relevance, diary-id granularity)
# --------------------------------------------------------------------------- #
def recall_at_k(ranked: list[str], gold: set[str], k: int = FINAL_K) -> float:
    if not gold:
        return 0.0
    hits = sum(1 for diary_id in ranked[:k] if diary_id in gold)
    return hits / len(gold)


def reciprocal_rank(ranked: list[str], gold: set[str], k: int = FINAL_K) -> float:
    for index, diary_id in enumerate(ranked[:k]):
        if diary_id in gold:
            return 1.0 / (index + 1)
    return 0.0


def ndcg_at_k(ranked: list[str], gold: set[str], k: int = FINAL_K) -> float:
    if not gold:
        return 0.0
    dcg = sum(
        1.0 / math.log2(index + 2)
        for index, diary_id in enumerate(ranked[:k])
        if diary_id in gold
    )
    ideal_hits = min(len(gold), k)
    idcg = sum(1.0 / math.log2(index + 2) for index in range(ideal_hits))
    return dcg / idcg if idcg > 0 else 0.0


# --------------------------------------------------------------------------- #
# Branch construction + execution
# --------------------------------------------------------------------------- #
def _build_branches(
    bm25_index: BM25Index,
    vector_collection: DiaryCollectionManager | None,
    reranker: Reranker | None,
) -> dict[str, HybridRetriever]:
    """Map branch name -> a HybridRetriever wired for that single configuration."""
    branches: dict[str, HybridRetriever] = {
        "bm25": HybridRetriever(_EmptyCollections(), bm25_index, final_top_k=FINAL_K),
    }
    if vector_collection is not None:
        branches["vector"] = HybridRetriever(
            vector_collection, BM25Index(), final_top_k=FINAL_K
        )
        branches["hybrid_rrf"] = HybridRetriever(
            vector_collection, bm25_index, final_top_k=FINAL_K
        )
        if reranker is not None:
            branches["hybrid_rerank"] = HybridRetriever(
                vector_collection, bm25_index, reranker=reranker, final_top_k=FINAL_K
            )
    return branches


def _rank_diaries(retriever: HybridRetriever, query: str) -> list[str]:
    return [result.diary_id for result in retriever.retrieve(query, top_k=FINAL_K)]


def _evaluate(
    branches: dict[str, HybridRetriever],
    cases: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, float]], list[str]]:
    """Return per-branch averaged metrics and human-readable failure samples."""
    sums: dict[str, dict[str, float]] = {
        name: dict.fromkeys(METRIC_KEYS, 0.0) for name in branches
    }
    failures: list[str] = []

    for case in cases:
        gold = set(case["relevant_diary_ids"])
        for name, retriever in branches.items():
            ranked = _rank_diaries(retriever, case["query"])
            sums[name]["recall@5"] += recall_at_k(ranked, gold)
            sums[name]["mrr"] += reciprocal_rank(ranked, gold)
            sums[name]["ndcg@5"] += ndcg_at_k(ranked, gold)
            if not (gold & set(ranked[:FINAL_K])):
                failures.append(
                    f"  [{name}] {case['query_id']} {case['query']!r} "
                    f"intent={case['intent']} gold={sorted(gold)} "
                    f"top5={ranked[:FINAL_K]}"
                )

    n = len(cases)
    metrics = {
        name: {key: round(total / n, 4) for key, total in scores.items()}
        for name, scores in sums.items()
    }
    return metrics, failures


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def _print_report(
    metrics: dict[str, dict[str, float]],
    failures: list[str],
    skipped: dict[str, str],
) -> None:
    print("\n" + "=" * 64)
    print("RAG retrieval baseline (fixed corpus: 30 diaries x 20 queries)")
    print("=" * 64)
    header = f"{'branch':<16}{'Recall@5':>10}{'MRR':>10}{'nDCG@5':>10}"
    print(header)
    print("-" * len(header))
    order = ["bm25", "vector", "hybrid_rrf", "hybrid_rerank"]
    for name in order:
        if name in metrics:
            m = metrics[name]
            print(
                f"{name:<16}{m['recall@5']:>10.4f}{m['mrr']:>10.4f}{m['ndcg@5']:>10.4f}"
            )
        elif name in skipped:
            print(f"{name:<16}{'SKIPPED':>10}  ({skipped[name]})")
    if failures:
        print("\nFailure samples (branch missed all gold in top-5):")
        for line in failures:
            print(line)
    print("=" * 64 + "\n")


def _load_baseline() -> dict[str, dict[str, float]] | None:
    if not BASELINE_PATH.exists():
        return None
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def _write_baseline(metrics: dict[str, dict[str, float]]) -> None:
    BASELINE_PATH.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


# --------------------------------------------------------------------------- #
# The report fixture computes everything once; the tests assert on it
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def eval_report(
    eval_cases: list[dict[str, Any]],
    bm25_index: BM25Index,
    vector_collection: DiaryCollectionManager | None,
    reranker: Reranker | None,
) -> dict[str, Any]:
    branches = _build_branches(bm25_index, vector_collection, reranker)

    skipped: dict[str, str] = {}
    if vector_collection is None:
        skipped["vector"] = "chromadb/embedding model unavailable"
        skipped["hybrid_rrf"] = "no vector branch"
        skipped["hybrid_rerank"] = "no vector branch"
    elif reranker is None:
        skipped["hybrid_rerank"] = "reranker model not loaded"

    metrics, failures = _evaluate(branches, eval_cases)
    _print_report(metrics, failures, skipped)

    if os.getenv("EVAL_UPDATE_BASELINE") == "1":
        _write_baseline(metrics)
        print(f"[baseline] wrote {BASELINE_PATH.name} for branches: {sorted(metrics)}")

    return {"metrics": metrics, "skipped": skipped, "failures": failures}


def test_bm25_branch_runs(eval_report: dict[str, Any]) -> None:
    """BM25-only must always run and find at least some relevant diaries."""
    assert "bm25" in eval_report["metrics"]
    assert eval_report["metrics"]["bm25"]["recall@5"] > 0.0


def test_vector_branch(eval_report: dict[str, Any]) -> None:
    if "vector" not in eval_report["metrics"]:
        pytest.skip(eval_report["skipped"].get("vector", "vector branch unavailable"))
    assert eval_report["metrics"]["vector"]["recall@5"] >= 0.0


def test_hybrid_rrf_branch(eval_report: dict[str, Any]) -> None:
    if "hybrid_rrf" not in eval_report["metrics"]:
        pytest.skip(eval_report["skipped"].get("hybrid_rrf", "hybrid branch unavailable"))
    assert eval_report["metrics"]["hybrid_rrf"]["recall@5"] >= 0.0


def test_hybrid_rerank_branch(eval_report: dict[str, Any]) -> None:
    if "hybrid_rerank" not in eval_report["metrics"]:
        pytest.skip(
            eval_report["skipped"].get("hybrid_rerank", "rerank branch unavailable")
        )
    assert eval_report["metrics"]["hybrid_rerank"]["recall@5"] >= 0.0


def test_no_regression_vs_baseline(eval_report: dict[str, Any]) -> None:
    """Per-branch soft check: fail only on a real drop below the recorded value."""
    baseline = _load_baseline()
    if baseline is None:
        pytest.skip(
            "no baseline.json; seed with EVAL_UPDATE_BASELINE=1 make eval-rag"
        )

    regressions: list[str] = []
    for branch, scores in eval_report["metrics"].items():
        if branch not in baseline:
            continue
        for key in METRIC_KEYS:
            recorded = baseline[branch].get(key)
            current = scores.get(key)
            if recorded is None or current is None:
                continue
            if current < recorded - REGRESSION_TOLERANCE:
                regressions.append(
                    f"{branch}.{key}: {current:.4f} < {recorded:.4f} - {REGRESSION_TOLERANCE}"
                )

    assert not regressions, "Retrieval regression vs baseline:\n" + "\n".join(regressions)
