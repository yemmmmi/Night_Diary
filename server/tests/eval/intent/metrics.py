"""Pure metric functions for the chat-intent classification eval (事项3 PR-B).

No I/O, no fixtures — just deterministic scoring of predicted intents against
the gold annotations. Imported by ``conftest.py`` / ``test_eval_intent.py``.

The eval compares two LLM-layer strategies on top of the *same* rule layer:

- **Baseline A** — rule layer + general-purpose LLM (current production config).
- **Treatment B** — rule layer + fine-tuned small model (stub placeholder until
  the fine-tune is done; swapped in by replacing the LLM fixture).

Metric glossary
---------------
- accuracy                 : overall exact-match accuracy over all cases.
- macro_f1                 : macro-averaged F1 across the intent classes.
- weighted_f1              : support-weighted F1 across the intent classes.
- per_class_precision      : {intent: P} per class.
- per_class_recall         : {intent: R} per class.
- per_class_f1             : {intent: F1} per class.
- confusion_matrix         : NxN count matrix (rows = gold, cols = predicted),
                             where N == len(INTENT_LABELS).
- rule_short_circuit_rate  : fraction of cases the rule layer short-circuited
                             (confidence > 0.9). A property of the rule layer,
                             identical for A and B.
- llm_layer_accuracy       : accuracy over the *non-short-circuit* subset
                             (cases that actually reached the LLM layer).
- avg_latency_ms           : mean per-case classify latency (rule + llm).
                             Short-circuit cases contribute ~0 (rule-only).
- avg_tokens_per_call      : mean tokens consumed by the LLM layer, averaged
                             over cases that actually invoked the LLM.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.domain.agents.types import ChatIntent

#: Fixed label order used everywhere (rows/cols of the confusion matrix,
#: keys of the per-class dicts). Kept in sync with ``ChatIntent``. The six
#: original intents keep their positions; the P2 additions (plan_exploration,
#: task_command) are appended so existing matrix rows/cols stay stable.
INTENT_LABELS: tuple[str, ...] = (
    ChatIntent.CASUAL_CHAT.value,
    ChatIntent.EMOTIONAL_VENT.value,
    ChatIntent.RETROSPECTIVE_QUERY.value,
    ChatIntent.ADVICE_SEEKING.value,
    ChatIntent.CRISIS_SIGNAL.value,
    ChatIntent.ENTITY_QUERY.value,
    ChatIntent.PLAN_EXPLORATION.value,
    ChatIntent.TASK_COMMAND.value,
)

#: Scalar (non-dict) metric keys — the ones a baseline round-trips and the
#: regression guard watches. Dict-valued metrics (per_class_*, confusion_matrix)
#: and raw counts are reported but not regression-checked.
SCALAR_KEYS: tuple[str, ...] = (
    "accuracy",
    "macro_f1",
    "weighted_f1",
    "rule_short_circuit_rate",
    "llm_layer_accuracy",
    "avg_latency_ms",
    "avg_tokens_per_call",
)

#: "Higher is better" metrics (a drop below baseline is a regression).
ACCURACY_METRICS: tuple[str, ...] = (
    "accuracy",
    "macro_f1",
    "weighted_f1",
    "llm_layer_accuracy",
)

#: "Lower is better" cost metrics (a rise above baseline is a regression).
COST_METRICS: tuple[str, ...] = (
    "avg_latency_ms",
    "avg_tokens_per_call",
)


@dataclass
class CaseOutcome:
    """A single case's prediction aligned against its gold intent."""

    case_id: str
    category: str
    gold_intent: str
    predicted_intent: str
    #: True when the rule layer short-circuited (confidence > 0.9); the LLM
    #: layer was *not* consulted for this case.
    rule_short_circuited: bool
    #: True when the LLM layer was actually invoked (non-short-circuit and an
    #: LLM is wired). Drives token / latency accounting.
    llm_invoked: bool
    latency_ms: float
    tokens: int
    rule_confidence: float = 0.0
    notes: str = ""


def _confusion_matrix(
    outcomes: list[CaseOutcome], labels: tuple[str, ...]
) -> list[list[int]]:
    """Build a ``len(labels)`` x ``len(labels)`` count matrix (rows=gold)."""
    idx = {label: i for i, label in enumerate(labels)}
    n = len(labels)
    matrix = [[0] * n for _ in range(n)]
    for o in outcomes:
        gold = idx.get(o.gold_intent)
        pred = idx.get(o.predicted_intent)
        # Unknown labels land nowhere (shouldn't happen with the 6 canonical
        # intents); guard so a stray prediction can't crash the matrix.
        if gold is not None and pred is not None:
            matrix[gold][pred] += 1
    return matrix


def _per_class_prf(
    outcomes: list[CaseOutcome], labels: tuple[str, ...]
) -> tuple[
    dict[str, float],
    dict[str, float],
    dict[str, float],
    dict[str, dict[str, int]],
]:
    """Compute per-class precision / recall / F1 plus support counts."""
    stats: dict[str, dict[str, int]] = {
        label: {"tp": 0, "fp": 0, "fn": 0, "support": 0} for label in labels
    }
    for o in outcomes:
        gold = o.gold_intent
        pred = o.predicted_intent
        if gold in stats:
            stats[gold]["support"] += 1
        if pred == gold:
            if gold in stats:
                stats[gold]["tp"] += 1
        else:
            if gold in stats:
                stats[gold]["fn"] += 1
            if pred in stats:
                stats[pred]["fp"] += 1

    precision: dict[str, float] = {}
    recall: dict[str, float] = {}
    f1: dict[str, float] = {}
    for label in labels:
        s = stats[label]
        denom_p = s["tp"] + s["fp"]
        denom_r = s["tp"] + s["fn"]
        p = s["tp"] / denom_p if denom_p > 0 else 0.0
        r = s["tp"] / denom_r if denom_r > 0 else 0.0
        f = (2 * p * r) / (p + r) if (p + r) > 0 else 0.0
        precision[label] = p
        recall[label] = r
        f1[label] = f
    return precision, recall, f1, stats


def compute_metrics(outcomes: list[CaseOutcome]) -> dict[str, Any]:
    """Aggregate all metrics over a list of case outcomes.

    Returns a dict containing the scalar metrics (``SCALAR_KEYS``), the
    dict-valued ``per_class_*`` and ``confusion_matrix``, and raw counts
    (``n_cases`` / ``n_short_circuited`` / ``n_llm_invoked``).
    """
    n = len(outcomes)
    if n == 0:
        return _empty_metrics()

    correct = sum(o.predicted_intent == o.gold_intent for o in outcomes)
    accuracy = correct / n

    precision, recall, f1, stats = _per_class_prf(outcomes, INTENT_LABELS)
    macro_f1 = sum(f1[label] for label in INTENT_LABELS) / len(INTENT_LABELS)
    total_support = sum(stats[label]["support"] for label in INTENT_LABELS)
    weighted_f1 = (
        sum(f1[label] * stats[label]["support"] for label in INTENT_LABELS)
        / total_support
        if total_support > 0
        else 0.0
    )

    n_short_circuited = sum(o.rule_short_circuited for o in outcomes)
    rule_short_circuit_rate = n_short_circuited / n

    non_sc = [o for o in outcomes if not o.rule_short_circuited]
    llm_layer_accuracy = (
        sum(o.predicted_intent == o.gold_intent for o in non_sc) / len(non_sc)
        if non_sc
        else 0.0
    )

    avg_latency_ms = sum(o.latency_ms for o in outcomes) / n

    llm_calls = [o for o in outcomes if o.llm_invoked]
    avg_tokens_per_call = (
        sum(o.tokens for o in llm_calls) / len(llm_calls) if llm_calls else 0.0
    )

    return {
        "accuracy": round(accuracy, 4),
        "macro_f1": round(macro_f1, 4),
        "weighted_f1": round(weighted_f1, 4),
        "per_class_precision": {label: round(precision[label], 4) for label in INTENT_LABELS},
        "per_class_recall": {label: round(recall[label], 4) for label in INTENT_LABELS},
        "per_class_f1": {label: round(f1[label], 4) for label in INTENT_LABELS},
        "confusion_matrix": _confusion_matrix(outcomes, INTENT_LABELS),
        "rule_short_circuit_rate": round(rule_short_circuit_rate, 4),
        "llm_layer_accuracy": round(llm_layer_accuracy, 4),
        "avg_latency_ms": round(avg_latency_ms, 4),
        "avg_tokens_per_call": round(avg_tokens_per_call, 2),
        "n_cases": n,
        "n_short_circuited": n_short_circuited,
        "n_llm_invoked": len(llm_calls),
    }


def compute_metrics_by_category(
    outcomes: list[CaseOutcome],
) -> dict[str, dict[str, Any]]:
    """Per-category breakdown keyed by the dataset's ``category`` field.

    Only the scalar metrics + ``n_cases`` are reported per category (the
    confusion matrix is meaningless on tiny slices).
    """
    by_cat: dict[str, list[CaseOutcome]] = {}
    for o in outcomes:
        by_cat.setdefault(o.category, []).append(o)
    result: dict[str, dict[str, Any]] = {}
    for cat, items in by_cat.items():
        full = compute_metrics(items)
        result[cat] = {k: full[k] for k in SCALAR_KEYS}
        result[cat]["n_cases"] = full["n_cases"]
    return result


def _empty_metrics() -> dict[str, Any]:
    return {
        "accuracy": 0.0,
        "macro_f1": 0.0,
        "weighted_f1": 0.0,
        "per_class_precision": {label: 0.0 for label in INTENT_LABELS},
        "per_class_recall": {label: 0.0 for label in INTENT_LABELS},
        "per_class_f1": {label: 0.0 for label in INTENT_LABELS},
        "confusion_matrix": [[0] * len(INTENT_LABELS) for _ in INTENT_LABELS],
        "rule_short_circuit_rate": 0.0,
        "llm_layer_accuracy": 0.0,
        "avg_latency_ms": 0.0,
        "avg_tokens_per_call": 0.0,
        "n_cases": 0,
        "n_short_circuited": 0,
        "n_llm_invoked": 0,
    }


__all__ = [
    "ACCURACY_METRICS",
    "COST_METRICS",
    "INTENT_LABELS",
    "SCALAR_KEYS",
    "CaseOutcome",
    "compute_metrics",
    "compute_metrics_by_category",
]
