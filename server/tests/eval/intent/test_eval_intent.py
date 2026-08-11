"""Chat-intent classification eval: Baseline A vs Treatment B (事项3 PR-B).

Runs each annotated case through both LLM-layer strategies on top
of the shared rule layer, computes the metric block (accuracy / macro_f1 /
weighted_f1 / per-class P/R/F1 / NxN confusion matrix / rule short-circuit
rate / llm-layer accuracy / avg latency / avg tokens), prints an A/B
comparison table + per-class P/R/F1 + per-category accuracy + failure samples,
and guards against regression vs a recorded ``baseline.json``.

Out of CI; run via::

    make eval-intent                              # report + regression check
    EVAL_UPDATE_BASELINE=1 make eval-intent       # (re)seed baseline.json

See ``BASELINE.md`` for the protocol design and recorded values.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from app.domain.agents.chat_intent_classifier import ChatIntentClassifier
from tests.eval.intent.conftest import RecordingLLM, run_case
from tests.eval.intent.metrics import (
    ACCURACY_METRICS,
    COST_METRICS,
    INTENT_LABELS,
    SCALAR_KEYS,
    CaseOutcome,
    compute_metrics,
    compute_metrics_by_category,
)

# Excluded from the default test run (CI); selected only via `make eval-intent`.
pytestmark = pytest.mark.eval

#: Absolute tolerance for accuracy metrics: a drop beyond this below the
#: recorded baseline is a real regression to explain/fix.
REGRESSION_TOLERANCE = 0.05
#: Relative tolerance for cost metrics: a rise beyond (1 + this) above the
#: recorded baseline is a cost regression.
COST_REGRESSION_TOLERANCE = 0.25

BASELINE_PATH = Path(__file__).parent / "baseline.json"


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def _print_report(
    baseline_a: dict[str, Any],
    treatment_b: dict[str, Any],
    a_by_cat: dict[str, dict[str, Any]],
    b_by_cat: dict[str, dict[str, Any]],
    failures_a: list[str],
    failures_b: list[str],
    real_mode: bool,
    model_name: str,
    n_cases: int,
) -> None:
    sep = "=" * 92
    print("\n" + sep)
    mode = f"{model_name} (REAL)" if real_mode else "stub"
    print(f"Chat-intent classification A/B ({mode}, {n_cases} cases x 2 strategies)")
    print(sep)

    # Scalar comparison table
    header = (
        f"{'strategy':<14}{'accuracy':>10}{'macro_f1':>10}{'weighted_f1':>12}"
        f"{'sc_rate':>9}{'llm_acc':>9}{'lat_ms':>9}{'tok/call':>10}"
    )
    print(header)
    print("-" * len(header))
    for name, m in (("baseline_a", baseline_a), ("treatment_b", treatment_b)):
        print(
            f"{name:<14}"
            f"{m['accuracy']:>10.4f}"
            f"{m['macro_f1']:>10.4f}"
            f"{m['weighted_f1']:>12.4f}"
            f"{m['rule_short_circuit_rate']:>9.4f}"
            f"{m['llm_layer_accuracy']:>9.4f}"
            f"{m['avg_latency_ms']:>9.3f}"
            f"{m['avg_tokens_per_call']:>10.2f}"
        )

    # Delta row (Treatment B - Baseline A) on accuracy-style metrics
    print("\nDelta (treatment_b - baseline_a):")
    for key in ACCURACY_METRICS:
        delta = treatment_b[key] - baseline_a[key]
        sign = "+" if delta >= 0 else ""
        print(f"  {key:<22}{sign}{delta:.4f}")

    # Per-class P/R/F1 (Baseline A / Treatment B side by side)
    print("\nPer-class precision / recall / F1 (baseline_a | treatment_b):")
    print(
        f"  {'class':<22}{'P_a':>8}{'R_a':>8}{'F1_a':>8}"
        f"{'P_b':>8}{'R_b':>8}{'F1_b':>8}"
    )
    for label in INTENT_LABELS:
        pa = baseline_a["per_class_precision"][label]
        ra = baseline_a["per_class_recall"][label]
        fa = baseline_a["per_class_f1"][label]
        pb = treatment_b["per_class_precision"][label]
        rb = treatment_b["per_class_recall"][label]
        fb = treatment_b["per_class_f1"][label]
        print(
            f"  {label:<22}{pa:>8.3f}{ra:>8.3f}{fa:>8.3f}"
            f"{pb:>8.3f}{rb:>8.3f}{fb:>8.3f}"
        )

    # Confusion matrix (Baseline A)
    print("\nConfusion matrix (baseline_a, rows=gold, cols=predicted):")
    print("  " + " ".join(f"{label[:6]:>7}" for label in INTENT_LABELS))
    for i, label in enumerate(INTENT_LABELS):
        row = baseline_a["confusion_matrix"][i]
        print(f"  {label[:6]:<7}" + " ".join(f"{c:>7}" for c in row))

    # Per-category accuracy (A / B)
    print("\nPer-category accuracy (baseline_a / treatment_b):")
    cats = sorted(set(a_by_cat) | set(b_by_cat))
    for cat in cats:
        a_acc = a_by_cat.get(cat, {}).get("accuracy", 0.0)
        b_acc = b_by_cat.get(cat, {}).get("accuracy", 0.0)
        n = a_by_cat.get(cat, {}).get("n_cases", b_by_cat.get(cat, {}).get("n_cases", 0))
        print(f"  {cat:<48}{a_acc:>8.4f}{b_acc:>10.4f}{n:>6}")

    # Failure samples (mispredicted, non-short-circuit — the LLM layer's job)
    def _print_failures(label: str, failures: list[str]) -> None:
        if not failures:
            return
        print(f"\n{label} mispredictions (LLM-layer, first 20):")
        for line in failures[:20]:
            print(line)
        if len(failures) > 20:
            print(f"  ... {len(failures) - 20} more")

    _print_failures("baseline_a", failures_a)
    _print_failures("treatment_b", failures_b)
    print(sep + "\n")


def _collect_failures(outcomes: list[CaseOutcome], limit: int = 20) -> list[str]:
    """Format mispredictions among non-short-circuit cases (the LLM layer's job)."""
    failures: list[str] = []
    for o in outcomes:
        if o.rule_short_circuited:
            continue  # rule layer owned this case; not an LLM-layer failure
        if o.predicted_intent != o.gold_intent:
            failures.append(
                f"  {o.case_id} ({o.category}) "
                f"gold={o.gold_intent} pred={o.predicted_intent} "
                f"rule_conf={o.rule_confidence:.2f} | {o.notes}"
            )
        if len(failures) >= limit:
            break
    return failures


def _load_baseline() -> dict[str, Any] | None:
    if not BASELINE_PATH.exists():
        return None
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def _write_baseline(
    baseline_a: dict[str, Any], treatment_b: dict[str, Any]
) -> None:
    """Persist the scalar metric block for both strategies (round-trippable)."""
    payload = {
        "_placeholder": False,
        "_note": (
            "Seeded by EVAL_UPDATE_BASELINE=1 make eval-intent. "
            "Scalar metrics only; per_class_* and confusion_matrix are "
            "reported in stdout but not persisted here."
        ),
        "baseline_a": {k: baseline_a[k] for k in SCALAR_KEYS},
        "treatment_b": {k: treatment_b[k] for k in SCALAR_KEYS},
    }
    BASELINE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


# --------------------------------------------------------------------------- #
# The report fixture runs everything once; tests assert on it
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def eval_report(
    eval_cases: list[dict[str, Any]],
    baseline_a_classifier: ChatIntentClassifier,
    treatment_b_classifier: ChatIntentClassifier,
    baseline_a_llm: RecordingLLM,
    treatment_b_llm: RecordingLLM,
    rule_classifier: ChatIntentClassifier,
    real_mode: bool,
    model_name: str,
) -> dict[str, Any]:
    a_outcomes: list[CaseOutcome] = []
    b_outcomes: list[CaseOutcome] = []

    for case in eval_cases:
        a_outcomes.append(
            run_case(case, baseline_a_classifier, baseline_a_llm, rule_classifier)
        )
        b_outcomes.append(
            run_case(case, treatment_b_classifier, treatment_b_llm, rule_classifier)
        )

    baseline_a = compute_metrics(a_outcomes)
    treatment_b = compute_metrics(b_outcomes)
    a_by_cat = compute_metrics_by_category(a_outcomes)
    b_by_cat = compute_metrics_by_category(b_outcomes)

    failures_a = _collect_failures(a_outcomes)
    failures_b = _collect_failures(b_outcomes)

    _print_report(
        baseline_a,
        treatment_b,
        a_by_cat,
        b_by_cat,
        failures_a,
        failures_b,
        real_mode,
        model_name,
        len(eval_cases),
    )

    if os.getenv("EVAL_UPDATE_BASELINE") == "1":
        _write_baseline(baseline_a, treatment_b)
        print(
            f"[baseline] wrote {BASELINE_PATH.name} "
            f"(baseline_a + treatment_b) for {len(eval_cases)} cases"
        )

    return {
        "baseline_a": baseline_a,
        "treatment_b": treatment_b,
        "baseline_a_by_category": a_by_cat,
        "treatment_b_by_category": b_by_cat,
        "baseline_a_outcomes": a_outcomes,
        "treatment_b_outcomes": b_outcomes,
        "failures_a": failures_a,
        "failures_b": failures_b,
        "real_mode": real_mode,
        "model_name": model_name,
        "n_cases": len(eval_cases),
    }


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
_EXPECTED_GOLD_INTENTS = {
    "casual_chat",
    "emotional_vent",
    "retrospective_query",
    "advice_seeking",
    "crisis_signal",
    "entity_query",
    # P2 additions (PlannerAgent trigger intents)
    "plan_exploration",
    "task_command",
}

#: The dataset is expected to hold this many annotated cases. Update when the
#: corpus is deliberately expanded (e.g. adding cases for a new intent).
EXPECTED_CASE_COUNT = 250


def test_dataset_integrity(eval_cases: list[dict[str, Any]]) -> None:
    """The dataset must be N cases, 8 gold intents, unique ids, well-formed."""
    assert len(eval_cases) == EXPECTED_CASE_COUNT, (
        f"expected {EXPECTED_CASE_COUNT} cases, got {len(eval_cases)}"
    )

    seen: set[str] = set()
    for c in eval_cases:
        assert c["case_id"] not in seen, f"duplicate case_id: {c['case_id']}"
        seen.add(c["case_id"])
        assert c.get("text"), f"{c['case_id']}: empty text"
        assert c["gold_intent"] in _EXPECTED_GOLD_INTENTS, (
            f"{c['case_id']}: unknown gold_intent {c.get('gold_intent')}"
        )
        assert isinstance(c.get("rule_confidence"), int | float), (
            f"{c['case_id']}: rule_confidence missing"
        )
        assert isinstance(c.get("rule_short_circuits"), bool), (
            f"{c['case_id']}: rule_short_circuits missing"
        )
        assert c.get("category"), f"{c['case_id']}: empty category"

    gold_counts = Counter(c["gold_intent"] for c in eval_cases)
    assert set(gold_counts) == _EXPECTED_GOLD_INTENTS, (
        f"gold intent set mismatch: {set(gold_counts)}"
    )


def test_rule_short_circuit_matches_dataset(
    eval_cases: list[dict[str, Any]],
    rule_classifier: ChatIntentClassifier,
) -> None:
    """The recomputed rule short-circuit flag must match the dataset annotation.

    This guards against silent drift in the rule layer vs the dataset that was
    built from it.
    """
    mismatches: list[str] = []
    for c in eval_cases:
        rule_result = rule_classifier._rule_classify(c["text"])
        actual = rule_result.confidence > ChatIntentClassifier.CONFIDENCE_THRESHOLD
        expected = bool(c["rule_short_circuits"])
        if actual != expected:
            mismatches.append(
                f"{c['case_id']}: recomputed={actual} dataset={expected} "
                f"conf={rule_result.confidence:.2f}"
            )
    assert not mismatches, (
        f"rule short-circuit drift ({len(mismatches)} cases):\n"
        + "\n".join(mismatches[:10])
    )


def test_baseline_a_runs(eval_report: dict[str, Any]) -> None:
    """Baseline A must produce a full metric block with sane ranges."""
    m = eval_report["baseline_a"]
    for key in SCALAR_KEYS:
        assert key in m, f"baseline_a missing metric {key}"
    assert 0.0 <= m["accuracy"] <= 1.0
    assert 0.0 <= m["macro_f1"] <= 1.0
    assert 0.0 <= m["weighted_f1"] <= 1.0
    assert 0.0 <= m["rule_short_circuit_rate"] <= 1.0
    assert 0.0 <= m["llm_layer_accuracy"] <= 1.0
    assert m["avg_latency_ms"] >= 0.0
    assert m["avg_tokens_per_call"] >= 0.0
    # confusion matrix is NxN (N == len(INTENT_LABELS)) and its total == n_cases
    cm = m["confusion_matrix"]
    n_labels = len(INTENT_LABELS)
    assert len(cm) == n_labels and all(len(row) == n_labels for row in cm)
    assert sum(sum(row) for row in cm) == eval_report["n_cases"]
    # per-class dicts cover all labels
    for key in ("per_class_precision", "per_class_recall", "per_class_f1"):
        assert set(m[key]) == set(INTENT_LABELS)


def test_treatment_b_runs(eval_report: dict[str, Any]) -> None:
    """Treatment B must produce a full metric block with sane ranges."""
    m = eval_report["treatment_b"]
    for key in SCALAR_KEYS:
        assert key in m, f"treatment_b missing metric {key}"
    assert 0.0 <= m["accuracy"] <= 1.0
    assert 0.0 <= m["macro_f1"] <= 1.0
    assert m["avg_tokens_per_call"] >= 0.0


def test_shared_short_circuit_partition(eval_report: dict[str, Any]) -> None:
    """A and B share the same rule layer, so their short-circuit rate must match.

    This invariant is structural: the rule layer decides short-circuiting before
    either LLM is consulted, so the partition (and ``n_short_circuited``) is
    identical regardless of the LLM strategy.
    """
    a = eval_report["baseline_a"]
    b = eval_report["treatment_b"]
    assert a["rule_short_circuit_rate"] == pytest.approx(b["rule_short_circuit_rate"])
    assert a["n_short_circuited"] == b["n_short_circuited"]


def test_stub_treatment_b_is_oracle(eval_report: dict[str, Any], real_mode: bool) -> None:
    """In stub mode Treatment B (oracle placeholder) must nail every LLM-layer case.

    This proves the eval wiring is correct: given the gold intent as the stub's
    reply, the classifier parses it and matches gold, so ``llm_layer_accuracy``
    lands at 1.0 on the non-short-circuit subset. Real mode is skipped (the
    real fine-tuned model is imperfect by design and replaces this placeholder).
    """
    if real_mode:
        pytest.skip("oracle check only applies to stub mode (placeholder fine-tune)")
    b = eval_report["treatment_b"]
    assert b["llm_layer_accuracy"] == pytest.approx(1.0), (
        "Treatment B stub is oracle; non-short-circuit accuracy must be 1.0"
    )
    assert b["n_llm_invoked"] == b["n_cases"] - b["n_short_circuited"]


def test_stub_baseline_a_echoes_rule_layer(
    eval_report: dict[str, Any],
    eval_cases: list[dict[str, Any]],
    rule_classifier: ChatIntentClassifier,
    real_mode: bool,
) -> None:
    """In stub mode Baseline A echoes the rule layer on *every* case.

    The rule-echo stub adds no corrective signal: for each case, Baseline A's
    prediction equals the rule layer's verdict (short-circuit cases return the
    rule result directly; non-short-circuit cases get the rule verdict echoed
    back by the stub). This pins the lower bound the real general LLM is
    expected to beat. Real mode is skipped.
    """
    if real_mode:
        pytest.skip("rule-echo check only applies to stub mode")
    a_outcomes = eval_report["baseline_a_outcomes"]
    b = eval_report["treatment_b"]

    mismatches: list[str] = []
    for case, outcome in zip(eval_cases, a_outcomes, strict=True):
        rule_pred = rule_classifier._rule_classify(case["text"]).intent_category
        if outcome.predicted_intent != rule_pred:
            mismatches.append(
                f"{outcome.case_id}: baseline_a={outcome.predicted_intent} "
                f"rule={rule_pred}"
            )
    assert not mismatches, (
        f"Baseline A stub must echo the rule layer ({len(mismatches)} drift):\n"
        + "\n".join(mismatches[:10])
    )

    # Echo can never beat the oracle: Baseline A accuracy <= Treatment B.
    assert eval_report["baseline_a"]["accuracy"] <= b["accuracy"] + 1e-9
    # And on the LLM-layer subset, echo inherits rule errors while oracle is
    # perfect — so the LLM-layer gap is non-negative.
    assert (
        eval_report["baseline_a"]["llm_layer_accuracy"]
        <= b["llm_layer_accuracy"] + 1e-9
    )


def test_no_regression_vs_baseline(eval_report: dict[str, Any], real_mode: bool) -> None:
    """Soft per-strategy check: fail only on a real drop/rise vs the baseline."""
    if not real_mode:
        pytest.skip("regression vs baseline only checked in real mode (LLM_API_KEY set)")
    baseline = _load_baseline()
    if not baseline or baseline.get("_placeholder"):
        pytest.skip(
            "placeholder baseline; seed with EVAL_UPDATE_BASELINE=1 make eval-intent"
        )

    regressions: list[str] = []
    for strategy in ("baseline_a", "treatment_b"):
        recorded = baseline.get(strategy, {})
        current = eval_report[strategy]

        # Higher-is-better: a drop beyond tolerance is a regression.
        for key in ACCURACY_METRICS:
            rec = recorded.get(key)
            cur = current.get(key)
            if rec is None or cur is None:
                continue
            if cur < rec - REGRESSION_TOLERANCE:
                regressions.append(
                    f"{strategy}.{key}: {cur:.4f} < {rec:.4f} "
                    f"- {REGRESSION_TOLERANCE}"
                )

        # Lower-is-better: a rise beyond (1 + tol) is a cost regression.
        for key in COST_METRICS:
            rec = recorded.get(key)
            cur = current.get(key)
            if rec is None or cur is None:
                continue
            if rec > 0 and cur > rec * (1.0 + COST_REGRESSION_TOLERANCE):
                regressions.append(
                    f"{strategy}.{key}: {cur:.4f} > {rec:.4f} "
                    f"x{1.0 + COST_REGRESSION_TOLERANCE:.2f}"
                )

    assert not regressions, (
        "Intent-classification regression vs baseline:\n" + "\n".join(regressions)
    )
