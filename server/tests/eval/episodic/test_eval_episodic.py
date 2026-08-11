"""Offline episodic memory retrieval baseline: jaccard vs vector vs vector+reranker.

Runs every branch through the *production* :class:`EpisodicMemory.retrieve_relevant`
by varying which injectables (``embedder`` / ``reranker``) are wired, computes
Recall@5 / MRR / nDCG@5 over the fixed 36-entry corpus + 20 queries (4
categories), prints a comparison table plus failure samples and a per-category
Recall@5 breakdown, and guards against per-branch regression versus a recorded
``baseline.json``.

Run it manually (out of CI):

    make eval-episodic                              # report + regression check
    EVAL_UPDATE_BASELINE=1 make eval-episodic       # (re)seed baseline.json

Metrics are reused verbatim from :mod:`tests.eval.episodic.metrics` (copied from
the RAG suite) so both retrieval evals report identical Recall@5 / MRR / nDCG@5.

See ``BASELINE.md`` for model versions, stub-vs-real semantics and recorded values.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from tests.eval.episodic.metrics import (
    FINAL_K,
    METRIC_KEYS,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
)

# Excluded from the default test run (CI); selected only via `make eval-episodic`.
pytestmark = pytest.mark.eval

# Absolute tolerance: small-sample fluctuation is allowed; a drop beyond this
# below the recorded baseline is treated as a real regression to explain/fix.
# Matches the RAG eval's tolerance.
REGRESSION_TOLERANCE = 0.05
BASELINE_PATH = Path(__file__).parent / "baseline.json"

# Branch display order (rows absent from `metrics` are reported as SKIPPED).
BRANCH_ORDER = ("jaccard", "vector", "vector_rerank")


# --------------------------------------------------------------------------- #
# Branch construction + execution
# --------------------------------------------------------------------------- #
def _build_branches(
    jaccard_memory: Any,
    vector_memory: Any,
    vector_rerank_memory: Any,
) -> dict[str, Any]:
    """Map branch name -> a populated EpisodicMemory wired for that config."""
    branches: dict[str, Any] = {"jaccard": jaccard_memory, "vector": vector_memory}
    if vector_rerank_memory is not None:
        branches["vector_rerank"] = vector_rerank_memory
    return branches


def _rank_entries(memory: Any, query: str, now: float) -> list[str]:
    """Run one retrieval and return the ranked entry ids (gold granularity)."""
    results = memory.retrieve_relevant(query=query, top_k=FINAL_K, now=now)
    return [entry.entry_id for entry in results]


def _evaluate(
    branches: dict[str, Any],
    cases: list[dict[str, Any]],
    now: float,
) -> tuple[dict[str, dict[str, float]], list[str], dict[str, dict[str, float]]]:
    """Return per-branch averaged metrics, failure samples and per-category Recall@5.

    Failure sample = a branch missed *all* gold ids in the top-K for a query.
    Per-category Recall@5 is an extra diagnostic (the dataset is designed so
    ``char_jaccard`` collapses on the semantic category); only the aggregate
    metrics feed the baseline / regression check.
    """
    sums: dict[str, dict[str, float]] = {name: dict.fromkeys(METRIC_KEYS, 0.0) for name in branches}
    # category -> branch -> [recall@5 per case]
    cat_recalls: dict[str, dict[str, list[float]]] = {}
    failures: list[str] = []

    for case in cases:
        gold = set(case["relevant_entry_ids"])
        category = case.get("category", "?")
        cat_recalls.setdefault(category, {name: [] for name in branches})
        for name, memory in branches.items():
            ranked = _rank_entries(memory, case["query"], now)
            r = recall_at_k(ranked, gold)
            sums[name]["recall@5"] += r
            sums[name]["mrr"] += reciprocal_rank(ranked, gold)
            sums[name]["ndcg@5"] += ndcg_at_k(ranked, gold)
            cat_recalls[category][name].append(r)
            if not (gold & set(ranked[:FINAL_K])):
                failures.append(
                    f"  [{name}] {case['query_id']} {case['query']!r} "
                    f"cat={category} gold={sorted(gold)} top5={ranked[:FINAL_K]}"
                )

    n = len(cases)
    metrics = {
        name: {key: round(total / n, 4) for key, total in scores.items()}
        for name, scores in sums.items()
    }
    by_category = {
        category: {
            name: round(sum(vals) / len(vals), 4) if vals else 0.0
            for name, vals in branches_map.items()
        }
        for category, branches_map in cat_recalls.items()
    }
    return metrics, failures, by_category


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def _print_report(
    metrics: dict[str, dict[str, float]],
    failures: list[str],
    skipped: dict[str, str],
    by_category: dict[str, dict[str, float]],
) -> None:
    print("\n" + "=" * 72)
    print("Episodic memory retrieval baseline (fixed corpus: 36 entries x 20 queries)")
    print("=" * 72)
    header = f"{'branch':<16}{'Recall@5':>10}{'MRR':>10}{'nDCG@5':>10}"
    print(header)
    print("-" * len(header))
    for name in BRANCH_ORDER:
        if name in metrics:
            m = metrics[name]
            print(f"{name:<16}{m['recall@5']:>10.4f}{m['mrr']:>10.4f}{m['ndcg@5']:>10.4f}")
        elif name in skipped:
            print(f"{name:<16}{'SKIPPED':>10}  ({skipped[name]})")

    print("\nRecall@5 by category (diagnostic; not part of regression):")
    cat_header = f"{'category':<14}" + "".join(f"{name:>16}" for name in BRANCH_ORDER)
    print(cat_header)
    print("-" * len(cat_header))
    for category in sorted(by_category):
        row = f"{category:<14}"
        for name in BRANCH_ORDER:
            val = by_category[category].get(name)
            row += f"{val:>16.4f}" if val is not None else f"{'-':>16}"
        print(row)

    if failures:
        print("\nFailure samples (branch missed all gold in top-5):")
        for line in failures:
            print(line)
    print("=" * 72 + "\n")


def _load_baseline() -> dict[str, Any] | None:
    if not BASELINE_PATH.exists():
        return None
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def _write_baseline(metrics: dict[str, dict[str, float]], placeholder: bool) -> None:
    """Persist metrics; tag ``_placeholder`` when only stub-mode numbers exist.

    Placeholder baselines are wiring smoke-checks, not retrieval-quality goals:
    the regression check skips them so a future real-mode run can replace them
    without a spurious failure.
    """
    payload: dict[str, Any] = {
        name: {key: scores[key] for key in METRIC_KEYS} for name, scores in metrics.items()
    }
    payload["_placeholder"] = placeholder
    BASELINE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


# --------------------------------------------------------------------------- #
# The report fixture computes everything once; the tests assert on it
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def eval_report(
    test_cases: list[dict[str, Any]],
    fixed_now: float,
    jaccard_memory: Any,
    vector_memory: Any,
    vector_rerank_memory: Any,
    real_embed_mode: bool,
    reranker: Any,
) -> dict[str, Any]:
    branches = _build_branches(jaccard_memory, vector_memory, vector_rerank_memory)

    skipped: dict[str, str] = {}
    if vector_rerank_memory is None:
        if not real_embed_mode:
            skipped["vector_rerank"] = "stub mode (no sentence-transformers)"
        elif reranker is None:
            skipped["vector_rerank"] = "reranker model not loaded"
        else:
            skipped["vector_rerank"] = "rerank branch unavailable"

    metrics, failures, by_category = _evaluate(branches, test_cases, fixed_now)
    _print_report(metrics, failures, skipped, by_category)

    if os.getenv("EVAL_UPDATE_BASELINE") == "1":
        # A placeholder baseline records stub-mode wiring numbers; real-mode
        # (BGE) numbers are the actual retrieval-quality contract.
        _write_baseline(metrics, placeholder=not real_embed_mode)
        print(
            f"[baseline] wrote {BASELINE_PATH.name} for branches: {sorted(metrics)} "
            f"(placeholder={not real_embed_mode})"
        )

    return {
        "metrics": metrics,
        "skipped": skipped,
        "failures": failures,
        "by_category": by_category,
    }


# --------------------------------------------------------------------------- #
# Per-branch tests
# --------------------------------------------------------------------------- #
def test_jaccard_branch_runs(eval_report: dict[str, Any]) -> None:
    """Jaccard-only must always run and find at least some relevant entries."""
    assert "jaccard" in eval_report["metrics"]
    assert eval_report["metrics"]["jaccard"]["recall@5"] > 0.0


def test_vector_branch(eval_report: dict[str, Any]) -> None:
    """Vector branch runs in both stub and real mode (Stub/BGE embedder)."""
    assert "vector" in eval_report["metrics"]
    assert eval_report["metrics"]["vector"]["recall@5"] >= 0.0


def test_vector_rerank_branch(eval_report: dict[str, Any]) -> None:
    if "vector_rerank" not in eval_report["metrics"]:
        pytest.skip(eval_report["skipped"].get("vector_rerank", "rerank branch unavailable"))
    assert eval_report["metrics"]["vector_rerank"]["recall@5"] >= 0.0


def test_no_regression_vs_baseline(eval_report: dict[str, Any]) -> None:
    """Per-branch soft check: fail only on a real drop below the recorded value.

    Skips when there is no baseline yet, or when the recorded baseline is a
    stub-mode placeholder (``_placeholder: true``) — those numbers are not a
    retrieval-quality contract and must not gate a future real-mode run.
    """
    baseline = _load_baseline()
    if baseline is None:
        pytest.skip("no baseline.json; seed with EVAL_UPDATE_BASELINE=1 make eval-episodic")
    if baseline.get("_placeholder"):
        pytest.skip(
            "baseline.json is a stub-mode placeholder; reseed in real mode "
            "(pip install -e '.[eval]') to record a retrieval-quality contract"
        )

    regressions: list[str] = []
    for branch, scores in eval_report["metrics"].items():
        recorded_branch = baseline.get(branch)
        if not isinstance(recorded_branch, dict):
            continue
        for key in METRIC_KEYS:
            recorded = recorded_branch.get(key)
            current = scores.get(key)
            if recorded is None or current is None:
                continue
            if current < recorded - REGRESSION_TOLERANCE:
                regressions.append(
                    f"{branch}.{key}: {current:.4f} < {recorded:.4f} - {REGRESSION_TOLERANCE}"
                )

    assert not regressions, "Episodic retrieval regression vs baseline:\n" + "\n".join(regressions)
