"""Pure metric functions for the skill-routing clarification eval (B4).

No I/O, no fixtures — just deterministic scoring of predicted routing outcomes
against the annotated expectations. Imported by ``conftest.py`` /
``test_eval_skill_routing.py``.

Metric glossary
---------------
- routing_accuracy            : exact match of predicted vs expected outcome
                                over the 5-way outcome space
                                (clarify / record / insight / plan / chat).
- clarification_precision     : of the cases the router chose to clarify,
                                fraction that genuinely needed clarifying.
- clarification_recall        : of the cases that needed clarifying,
                                fraction the router actually clarified.
- clarification_f1            : harmonic mean of the two above.
- false_clarification_rate    : of the cases that should NOT clarify, fraction
                                the router interrupted anyway (over-asking).
- missed_clarification_rate   : of the cases that SHOULD clarify, fraction the
                                router guessed on silently (under-asking).
- avg_latency_ms              : mean per-case routing latency (rule + llm).
- avg_tokens_per_call         : mean tokens consumed by the router LLM,
                                averaged over cases that actually invoked it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Selection-quality metric keys (higher is better), watched by the regression guard.
QUALITY_METRIC_KEYS: tuple[str, ...] = (
    "routing_accuracy",
    "clarification_f1",
)

#: Cost/over-asking metric keys (lower is better), watched by the regression guard.
COST_METRIC_KEYS: tuple[str, ...] = ("false_clarification_rate",)

#: Efficiency metric keys (environment-dependent; reported, not regression-guarded).
EFFICIENCY_METRIC_KEYS: tuple[str, ...] = (
    "avg_latency_ms",
    "avg_tokens_per_call",
)

#: All metric keys, used by baseline round-trip + report.
METRIC_KEYS: tuple[str, ...] = (
    "routing_accuracy",
    "clarification_precision",
    "clarification_recall",
    "clarification_f1",
    "false_clarification_rate",
    "missed_clarification_rate",
    "avg_latency_ms",
    "avg_tokens_per_call",
)


@dataclass
class CaseOutcome:
    """A single case's routing decision aligned against its expectation."""

    case_id: str
    category: str
    expected_outcome: str
    predicted_outcome: str
    expected_source: str
    actual_source: str
    confidence: float = 1.0
    latency_ms: float = 0.0
    tokens: int = 0
    llm_invoked: bool = False

    @property
    def expected_clarify(self) -> bool:
        return self.expected_outcome == "clarify"

    @property
    def predicted_clarify(self) -> bool:
        return self.predicted_outcome == "clarify"


@dataclass
class CaseMetric:
    """Per-case scored metrics."""

    case_id: str
    category: str
    exact_match: bool
    expected_clarify: bool
    predicted_clarify: bool
    tp: int
    fp: int
    fn: int
    tn: int
    latency_ms: float
    tokens: int
    llm_invoked: bool


# --------------------------------------------------------------------------- #
# Per-case scoring
# --------------------------------------------------------------------------- #
def score_case(outcome: CaseOutcome) -> CaseMetric:
    """Score one case into clarification confusion counts + exact match."""
    exact_match = outcome.predicted_outcome == outcome.expected_outcome

    tp = int(outcome.expected_clarify and outcome.predicted_clarify)
    fp = int((not outcome.expected_clarify) and outcome.predicted_clarify)
    fn = int(outcome.expected_clarify and (not outcome.predicted_clarify))
    tn = int((not outcome.expected_clarify) and (not outcome.predicted_clarify))

    return CaseMetric(
        case_id=outcome.case_id,
        category=outcome.category,
        exact_match=exact_match,
        expected_clarify=outcome.expected_clarify,
        predicted_clarify=outcome.predicted_clarify,
        tp=tp,
        fp=fp,
        fn=fn,
        tn=tn,
        latency_ms=outcome.latency_ms,
        tokens=outcome.tokens,
        llm_invoked=outcome.llm_invoked,
    )


# --------------------------------------------------------------------------- #
# Aggregate metrics
# --------------------------------------------------------------------------- #
def compute_metrics(outcomes: list[CaseOutcome]) -> dict[str, float]:
    """Aggregate routing + clarification metrics over a list of case outcomes."""
    if not outcomes:
        return {k: 0.0 for k in METRIC_KEYS}

    metrics_list = [score_case(o) for o in outcomes]
    n = len(metrics_list)

    routing_accuracy = sum(m.exact_match for m in metrics_list) / n

    total_tp = sum(m.tp for m in metrics_list)
    total_fp = sum(m.fp for m in metrics_list)
    total_fn = sum(m.fn for m in metrics_list)
    total_tn = sum(m.tn for m in metrics_list)

    precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) else 1.0
    recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    false_clarification_rate = total_fp / (total_fp + total_tn) if (total_fp + total_tn) else 0.0
    missed_clarification_rate = total_fn / (total_tp + total_fn) if (total_tp + total_fn) else 0.0

    llm_cases = [m for m in metrics_list if m.llm_invoked]
    avg_latency_ms = sum(m.latency_ms for m in metrics_list) / n
    avg_tokens_per_call = sum(m.tokens for m in llm_cases) / len(llm_cases) if llm_cases else 0.0

    return {
        "routing_accuracy": round(routing_accuracy, 4),
        "clarification_precision": round(precision, 4),
        "clarification_recall": round(recall, 4),
        "clarification_f1": round(f1, 4),
        "false_clarification_rate": round(false_clarification_rate, 4),
        "missed_clarification_rate": round(missed_clarification_rate, 4),
        "avg_latency_ms": round(avg_latency_ms, 3),
        "avg_tokens_per_call": round(avg_tokens_per_call, 2),
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
    predicted_outcome: str,
    *,
    actual_source: str,
    confidence: float,
    latency_ms: float = 0.0,
    tokens: int = 0,
    llm_invoked: bool = False,
) -> CaseOutcome:
    """Build a :class:`CaseOutcome` from a raw case dict + predicted outcome."""
    return CaseOutcome(
        case_id=case["case_id"],
        category=case["category"],
        expected_outcome=case["expected_outcome"],
        predicted_outcome=predicted_outcome,
        expected_source=case["expected_source"],
        actual_source=actual_source,
        confidence=confidence,
        latency_ms=latency_ms,
        tokens=tokens,
        llm_invoked=llm_invoked,
    )


__all__ = [
    "COST_METRIC_KEYS",
    "EFFICIENCY_METRIC_KEYS",
    "METRIC_KEYS",
    "QUALITY_METRIC_KEYS",
    "CaseMetric",
    "CaseOutcome",
    "compute_metrics",
    "compute_metrics_by_category",
    "outcome_from_case",
    "score_case",
]
