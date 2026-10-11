"""Skill-routing clarification eval (B4) — acceptance gate for the intent router.

Runs the 31 annotated cases through the production router
(:func:`app.domain.skills.intent.classify_user_intent`), computes the routing +
clarification metric block (routing_accuracy / clarification P,R,F1 /
false_clarification_rate / missed_clarification_rate / avg_latency /
avg_tokens), prints a per-category breakdown + misrouted samples, and guards
against regression vs a recorded ``baseline.json``.

This is the eval gate the Hermes review (E2) asks for on top of B4: the
ambiguity-clarification improvement ships with its own offline acceptance
check, wired into the CI stub gate.

Out of CI by default; run via::

    make eval-routing                              # report + regression check
    EVAL_UPDATE_BASELINE=1 make eval-routing       # (re)seed baseline.json

See ``BASELINE.md`` for the protocol design and recorded values.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.domain.skills.intent import classify_user_intent
from tests.eval.skill_routing.conftest import RecordingLLM, run_case
from tests.eval.skill_routing.metrics import (
    COST_METRIC_KEYS,
    METRIC_KEYS,
    QUALITY_METRIC_KEYS,
    CaseOutcome,
    compute_metrics,
    compute_metrics_by_category,
)

# Excluded from the default test run (CI); selected only via `make eval-routing`.
pytestmark = pytest.mark.eval

#: Absolute tolerance for quality metrics: a drop beyond this below the
#: recorded baseline is a real regression to explain/fix.
REGRESSION_TOLERANCE = 0.05
BASELINE_PATH = Path(__file__).parent / "baseline.json"

_EXPECTED_CATEGORIES = {
    "ambiguous_skill",
    "confident_skill",
    "low_conf_chat",
    "strong_rule",
    "goal_rule",
    "no_signal_chat",
    "empty",
}
_EXPECTED_OUTCOMES = {"clarify", "record", "insight", "plan", "chat"}
_EXPECTED_SOURCES = {"llm", "rule", "goal_rule", "default"}

#: The dataset is expected to hold this many annotated cases. Update when the
#: corpus is deliberately expanded (e.g. adding a category).
EXPECTED_CASE_COUNT = 31


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def _print_report(
    metrics: dict[str, Any],
    by_cat: dict[str, dict[str, Any]],
    outcomes: list[CaseOutcome],
    real_mode: bool,
    model_name: str,
) -> None:
    sep = "=" * 92
    mode = f"{model_name} (REAL)" if real_mode else "stub (oracle)"
    print("\n" + sep)
    print(f"Skill-routing clarification eval ({mode}, {len(outcomes)} cases)")
    print(sep)

    print(
        f"{'routing_acc':>12}{'clr_P':>9}{'clr_R':>9}{'clr_F1':>9}"
        f"{'false_clr':>11}{'miss_clr':>10}{'lat_ms':>10}{'tok/call':>10}"
    )
    print("-" * 90)
    print(
        f"{metrics['routing_accuracy']:>12.4f}"
        f"{metrics['clarification_precision']:>9.4f}"
        f"{metrics['clarification_recall']:>9.4f}"
        f"{metrics['clarification_f1']:>9.4f}"
        f"{metrics['false_clarification_rate']:>11.4f}"
        f"{metrics['missed_clarification_rate']:>10.4f}"
        f"{metrics['avg_latency_ms']:>10.3f}"
        f"{metrics['avg_tokens_per_call']:>10.2f}"
    )

    print("\nPer-category (routing_acc / clr_f1 / n):")
    for cat in sorted(by_cat):
        m = by_cat[cat]
        n = sum(1 for o in outcomes if o.category == cat)
        print(f"  {cat:<20}{m['routing_accuracy']:>10.4f}" f"{m['clarification_f1']:>10.4f}{n:>6}")

    failures = [o for o in outcomes if o.predicted_outcome != o.expected_outcome]
    if failures:
        print(f"\nMisrouted ({len(failures)}, first 20):")
        for o in failures[:20]:
            print(
                f"  {o.case_id} ({o.category}) "
                f"expected={o.expected_outcome} predicted={o.predicted_outcome} "
                f"src={o.actual_source} conf={o.confidence:.2f}"
            )
    print(sep + "\n")


def _load_baseline() -> dict[str, Any] | None:
    if not BASELINE_PATH.exists():
        return None
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def _write_baseline(
    metrics: dict[str, Any],
    *,
    real_mode: bool,
    model_name: str,
    sample_count: int,
) -> None:
    """Persist the recorded baseline (placeholder flag mirrors stub vs real)."""
    payload = {
        "_placeholder": not real_mode,
        "_mode": "real" if real_mode else "stub_oracle",
        "_model": model_name if real_mode else "stub-oracle",
        "_sample_count": sample_count,
        "_seeded_at": datetime.now(UTC).isoformat(),
        "_runs": 1,
        "_note": (
            "stub mode is a deterministic oracle (all quality metrics pinned at "
            "1.0 / 0.0) and only proves the routing wiring; reseed in REAL mode "
            "for a meaningful regression floor."
        ),
        "metrics": {k: metrics[k] for k in METRIC_KEYS},
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
    router_llm: RecordingLLM,
    real_mode: bool,
    model_name: str,
) -> dict[str, Any]:
    outcomes = [run_case(case, router_llm) for case in eval_cases]
    metrics = compute_metrics(outcomes)
    by_cat = compute_metrics_by_category(outcomes)

    _print_report(metrics, by_cat, outcomes, real_mode, model_name)

    if os.getenv("EVAL_UPDATE_BASELINE") == "1":
        _write_baseline(
            metrics, real_mode=real_mode, model_name=model_name, sample_count=len(outcomes)
        )
        print(f"[baseline] wrote {BASELINE_PATH.name} for {len(outcomes)} cases")

    return {
        "metrics": metrics,
        "by_category": by_cat,
        "outcomes": outcomes,
        "real_mode": real_mode,
        "model_name": model_name,
        "n_cases": len(outcomes),
    }


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_dataset_integrity(eval_cases: list[dict[str, Any]]) -> None:
    """The dataset must be N well-formed cases with known categories/outcomes."""
    assert (
        len(eval_cases) == EXPECTED_CASE_COUNT
    ), f"expected {EXPECTED_CASE_COUNT} cases, got {len(eval_cases)}"

    seen: set[str] = set()
    for c in eval_cases:
        assert c["case_id"] not in seen, f"duplicate case_id: {c['case_id']}"
        seen.add(c["case_id"])
        assert (
            c["category"] in _EXPECTED_CATEGORIES
        ), f"{c['case_id']}: unknown category {c['category']}"
        assert (
            c["expected_outcome"] in _EXPECTED_OUTCOMES
        ), f"{c['case_id']}: unknown expected_outcome {c['expected_outcome']}"
        assert (
            c["expected_source"] in _EXPECTED_SOURCES
        ), f"{c['case_id']}: unknown expected_source {c['expected_source']}"
        assert c["stub_intent"] in (
            "record",
            "insight",
            "plan",
            "chat",
        ), f"{c['case_id']}: bad stub_intent {c['stub_intent']}"
        assert 0.0 <= c["stub_confidence"] <= 1.0, f"{c['case_id']}: stub_confidence out of range"

    counts = Counter(c["category"] for c in eval_cases)
    assert set(counts) == _EXPECTED_CATEGORIES, f"category set mismatch: {set(counts)}"


def test_rule_layer_matches_dataset(eval_cases: list[dict[str, Any]]) -> None:
    """The recomputed rule-layer source must match the dataset annotation.

    Guards against silent drift between the rule layer and the dataset built
    from it. ``llm=None`` is used so the weak-signal path degrades to the
    ``default`` source — which is exactly what the ``expected_source == "llm"``
    cases should do when no LLM is attached (proving they reach the LLM gate).
    """
    mismatches: list[str] = []
    for c in eval_cases:
        decision = classify_user_intent(c["text"], llm=None)
        expected = "default" if c["expected_source"] == "llm" else c["expected_source"]
        if decision.source != expected:
            mismatches.append(f"{c['case_id']}: recomputed={decision.source} dataset={expected}")
    assert not mismatches, f"rule-layer drift ({len(mismatches)} cases):\n" + "\n".join(
        mismatches[:10]
    )


def test_metrics_sane(eval_report: dict[str, Any]) -> None:
    """The metric block must be present and within [0, 1] / non-negative."""
    m = eval_report["metrics"]
    for key in METRIC_KEYS:
        assert key in m, f"missing metric {key}"
    for key in (*QUALITY_METRIC_KEYS, *COST_METRIC_KEYS):
        assert 0.0 <= m[key] <= 1.0, f"{key} out of range: {m[key]}"
    assert m["avg_latency_ms"] >= 0.0
    assert m["avg_tokens_per_call"] >= 0.0


def test_clarification_only_from_llm(eval_report: dict[str, Any]) -> None:
    """Structural invariant: only an uncertain LLM answer may trigger clarifying.

    A strong rule, a goal-shaped plan or a manual pick is always trusted, so no
    case whose decision came from the rule layer may be clarified.
    """
    bad = [o for o in eval_report["outcomes"] if o.predicted_clarify and o.actual_source != "llm"]
    assert not bad, "clarified a rule-layer decision: " + ", ".join(o.case_id for o in bad)


def test_stub_is_oracle(eval_report: dict[str, Any], real_mode: bool) -> None:
    """In stub mode the oracle input must nail every routing decision.

    This proves the eval wiring: the stub returns each case's annotated intent +
    confidence, so routing accuracy and clarification F1 land at 1.0. Real mode
    is skipped (the real router is imperfect by design).
    """
    if real_mode:
        pytest.skip("oracle check only applies to stub mode")
    m = eval_report["metrics"]
    assert m["routing_accuracy"] == pytest.approx(
        1.0
    ), "stub oracle must route every case correctly"
    assert m["clarification_f1"] == pytest.approx(
        1.0
    ), "stub oracle must clarify exactly the ambiguous cases"
    assert m["false_clarification_rate"] == pytest.approx(0.0)
    assert m["missed_clarification_rate"] == pytest.approx(0.0)


def test_no_regression_vs_baseline(eval_report: dict[str, Any], real_mode: bool) -> None:
    """Soft check: fail only on a real drop/rise vs the recorded baseline."""
    if not real_mode:
        pytest.skip("regression vs baseline only checked in real mode (LLM_API_KEY set)")
    baseline = _load_baseline()
    if not baseline or baseline.get("_placeholder"):
        pytest.skip("placeholder baseline; seed with EVAL_UPDATE_BASELINE=1 make eval-routing")

    recorded = baseline.get("metrics", {})
    current = eval_report["metrics"]
    regressions: list[str] = []

    for key in QUALITY_METRIC_KEYS:
        rec = recorded.get(key)
        if rec is not None and current[key] < rec - REGRESSION_TOLERANCE:
            regressions.append(f"{key}: {current[key]:.4f} < {rec:.4f} - {REGRESSION_TOLERANCE}")
    for key in COST_METRIC_KEYS:
        rec = recorded.get(key)
        if rec is not None and current[key] > rec + REGRESSION_TOLERANCE:
            regressions.append(f"{key}: {current[key]:.4f} > {rec:.4f} + {REGRESSION_TOLERANCE}")

    assert not regressions, "skill-routing regression vs baseline:\n" + "\n".join(regressions)
