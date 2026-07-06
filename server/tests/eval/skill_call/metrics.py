"""Pure metric functions for skill-call accuracy evaluation (progressive disclosure A/B).

No I/O, no fixtures — just deterministic scoring of predicted skill selections
against annotated expectations. Imported by ``conftest.py`` / ``test_eval_skill_call.py``.

Metric glossary
---------------
- skill_selection_accuracy : exact match of predicted vs expected skill set.
- skill_selection_f1       : micro-averaged set-level F1 (P=TP/pred, R=TP/exp).
- false_activation_rate    : of skills that should NOT activate, fraction falsely activated.
- missed_activation_rate   : of skills that should activate, fraction missed (= 1 - recall).
- avg_prompt_tokens        : mean estimated prompt tokens per case.
- avg_latency_ms           : mean LLM round-trip latency in milliseconds.
- avg_disclosure_rounds    : mean on-demand body-loading rounds (progressive only).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Selection metric keys (accuracy / F1 / FAR / MAR).
SELECTION_METRIC_KEYS: tuple[str, ...] = (
    "skill_selection_accuracy",
    "skill_selection_f1",
    "false_activation_rate",
    "missed_activation_rate",
)

#: Efficiency metric keys (tokens / latency / disclosure).
EFFICIENCY_METRIC_KEYS: tuple[str, ...] = (
    "avg_prompt_tokens",
    "avg_latency_ms",
    "avg_disclosure_rounds",
)

#: All metric keys (selection + efficiency), used by baseline round-trip + report.
METRIC_KEYS: tuple[str, ...] = SELECTION_METRIC_KEYS + EFFICIENCY_METRIC_KEYS


@dataclass
class CaseOutcome:
    """A single case's prediction aligned against its expectation."""

    case_id: str
    category: str
    available_skills: list[str]
    expected_skills: list[str]
    predicted_skills: list[str]
    prompt_tokens: int = 0
    latency_ms: float = 0.0
    disclosure_rounds: int = 0
    parse_ok: bool = True


@dataclass
class CaseMetric:
    """Per-case scored metrics (counts + derived 0..1 floats)."""

    case_id: str
    category: str
    exact_match: bool
    tp: int  # correctly activated
    fp: int  # falsely activated (should not)
    fn: int  # missed (should have)
    tn: int  # correctly not activated
    precision: float
    recall: float
    f1: float
    prompt_tokens: int
    latency_ms: float
    disclosure_rounds: int


# --------------------------------------------------------------------------- #
# Per-case scoring
# --------------------------------------------------------------------------- #
def score_case(outcome: CaseOutcome) -> CaseMetric:
    """Score one case into per-case metrics (set-level P/R/F1 + counts)."""
    predicted = set(outcome.predicted_skills)
    expected = set(outcome.expected_skills)
    available = set(outcome.available_skills)

    should_activate = expected  # skills that SHOULD be on
    should_not = available - expected  # skills that should stay off

    tp = len(predicted & should_activate)
    fp = len(predicted - expected)  # predicted but not expected
    fn = len(expected - predicted)  # expected but not predicted
    tn = len(should_not - predicted)  # should-not and not predicted

    exact_match = predicted == expected

    # Per-case precision / recall / F1
    precision = tp / len(predicted) if predicted else (1.0 if not expected else 0.0)
    recall = tp / len(expected) if expected else 1.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    return CaseMetric(
        case_id=outcome.case_id,
        category=outcome.category,
        exact_match=exact_match,
        tp=tp,
        fp=fp,
        fn=fn,
        tn=tn,
        precision=precision,
        recall=recall,
        f1=f1,
        prompt_tokens=outcome.prompt_tokens,
        latency_ms=outcome.latency_ms,
        disclosure_rounds=outcome.disclosure_rounds,
    )


# --------------------------------------------------------------------------- #
# Aggregate metrics
# --------------------------------------------------------------------------- #
def compute_metrics(outcomes: list[CaseOutcome]) -> dict[str, float]:
    """Aggregate selection + efficiency metrics over a list of case outcomes.

    Uses **micro-averaging** for the set-level F1: pool TP/FP/FN across all
    cases, then compute P = total_TP / total_predicted, R = total_TP /
    total_expected, F1 = 2PR / (P+R).

    - ``false_activation_rate`` = total_FP / total_should_not_activate
      (of skills that should stay off, fraction falsely turned on).
    - ``missed_activation_rate`` = total_FN / total_expected
      (of skills that should be on, fraction missed = 1 - recall).
    """
    if not outcomes:
        return {k: 0.0 for k in METRIC_KEYS}

    metrics_list = [score_case(o) for o in outcomes]
    n = len(metrics_list)

    # --- Selection metrics (micro-averaged) ---
    accuracy = sum(m.exact_match for m in metrics_list) / n

    total_tp = sum(m.tp for m in metrics_list)
    total_fp = sum(m.fp for m in metrics_list)
    total_fn = sum(m.fn for m in metrics_list)
    total_tn = sum(m.tn for m in metrics_list)

    total_predicted = total_tp + total_fp
    total_expected = total_tp + total_fn
    total_should_not = total_fp + total_tn  # available - expected, summed

    micro_p = total_tp / total_predicted if total_predicted else 1.0
    micro_r = total_tp / total_expected if total_expected else 1.0
    micro_f1 = (
        2 * micro_p * micro_r / (micro_p + micro_r)
        if (micro_p + micro_r) > 0
        else 0.0
    )

    false_activation_rate = (
        total_fp / total_should_not if total_should_not else 0.0
    )
    missed_activation_rate = (
        total_fn / total_expected if total_expected else 0.0
    )

    # --- Efficiency metrics (simple means) ---
    avg_prompt_tokens = sum(m.prompt_tokens for m in metrics_list) / n
    avg_latency_ms = sum(m.latency_ms for m in metrics_list) / n
    avg_disclosure_rounds = sum(m.disclosure_rounds for m in metrics_list) / n

    return {
        "skill_selection_accuracy": round(accuracy, 4),
        "skill_selection_f1": round(micro_f1, 4),
        "false_activation_rate": round(false_activation_rate, 4),
        "missed_activation_rate": round(missed_activation_rate, 4),
        "avg_prompt_tokens": round(avg_prompt_tokens, 2),
        "avg_latency_ms": round(avg_latency_ms, 2),
        "avg_disclosure_rounds": round(avg_disclosure_rounds, 4),
    }


def compute_metrics_by_category(
    outcomes: list[CaseOutcome],
) -> dict[str, dict[str, float]]:
    """Per-category breakdown keyed by category name."""
    by_cat: dict[str, list[CaseOutcome]] = {}
    for o in outcomes:
        by_cat.setdefault(o.category, []).append(o)
    return {cat: compute_metrics(items) for cat, items in by_cat.items()}


# --------------------------------------------------------------------------- #
# Outcome factory
# --------------------------------------------------------------------------- #
def outcome_from_case(
    case: dict[str, Any],
    predicted_skills: list[str],
    *,
    prompt_tokens: int = 0,
    latency_ms: float = 0.0,
    disclosure_rounds: int = 0,
    parse_ok: bool = True,
) -> CaseOutcome:
    """Build a :class:`CaseOutcome` from a raw case dict + predicted skills."""
    return CaseOutcome(
        case_id=case["case_id"],
        category=case["category"],
        available_skills=list(case.get("available_skills", [])),
        expected_skills=list(case.get("expected_skills", [])),
        predicted_skills=list(predicted_skills),
        prompt_tokens=prompt_tokens,
        latency_ms=latency_ms,
        disclosure_rounds=disclosure_rounds,
        parse_ok=parse_ok,
    )


__all__ = [
    "EFFICIENCY_METRIC_KEYS",
    "METRIC_KEYS",
    "SELECTION_METRIC_KEYS",
    "CaseMetric",
    "CaseOutcome",
    "compute_metrics",
    "compute_metrics_by_category",
    "outcome_from_case",
    "score_case",
]
