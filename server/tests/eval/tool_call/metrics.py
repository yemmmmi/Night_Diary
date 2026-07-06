"""Pure metric functions for tool-call accuracy evaluation.

No I/O, no fixtures — just deterministic scoring of predicted tool calls against
annotated expectations. Imported by ``conftest.py`` / ``test_eval_tool_call.py``.

Metric glossary
---------------
- decision_accuracy     : did the model correctly decide call vs. no-call?
- tool_name_accuracy    : over should-call cases, Jaccard of predicted vs expected names.
- argument_accuracy     : over should-call cases, mean arg-match score.
- exact_match           : decision + names + args all correct.
- false_positive_rate   : should-NOT-call but did (per no-tool case).
- false_negative_rate   : should-call but did not (per tool case).
- parse_success_rate    : fallback-only; fraction of cases parsed cleanly.
- avg_tool_count        : mean number of tool calls produced per case.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: Ordered metric keys (used by baseline round-trip + report header).
METRIC_KEYS: tuple[str, ...] = (
    "decision_accuracy",
    "tool_name_accuracy",
    "argument_accuracy",
    "exact_match",
    "false_positive_rate",
    "false_negative_rate",
    "parse_success_rate",
    "avg_tool_count",
)


@dataclass(frozen=True)
class ExpectedCall:
    """One annotated expected tool call."""

    name: str
    args_match: dict[str, Any] = field(default_factory=dict)
    args_required: list[str] = field(default_factory=list)


@dataclass
class CaseOutcome:
    """A single case's prediction aligned against its expectation."""

    case_id: str
    category: str
    should_call: bool
    expected_calls: list[ExpectedCall]
    predicted_names: list[str]
    predicted_args_by_name: dict[str, dict[str, Any]]
    parse_ok: bool = True


@dataclass
class CaseMetric:
    """Per-case scored metrics (0/1 or 0..1 floats)."""

    case_id: str
    category: str
    decision_correct: bool
    name_score: float
    arg_score: float
    exact: bool
    false_positive: bool
    false_negative: bool
    parse_ok: bool
    tool_count: int


def _jaccard(a: list[str], b: list[str]) -> float:
    """Set similarity in [0,1]; 1.0 when both empty (vacuous agreement)."""
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _arg_score(
    predicted_args: dict[str, Any], expected: ExpectedCall
) -> float:
    """Fraction of required/matched args satisfied.

    A condition (arg name) is *satisfied* when present in ``predicted_args`` and,
    if ``args_match`` pins a value, that value matches. Tools with no conditions
    (e.g. ``get_weather_info``) score 1.0 vacuously.
    """
    conditions = set(expected.args_required) | set(expected.args_match.keys())
    if not conditions:
        return 1.0
    satisfied = 0
    for name in conditions:
        if name not in predicted_args:
            continue
        if name in expected.args_match:
            if predicted_args[name] == expected.args_match[name]:
                satisfied += 1
        else:
            satisfied += 1
    return satisfied / len(conditions)


def score_case(outcome: CaseOutcome) -> CaseMetric:
    """Score one case into per-case metrics."""
    predicted_count = len(outcome.predicted_names)
    decision_correct = (
        (outcome.should_call and predicted_count > 0)
        or (not outcome.should_call and predicted_count == 0)
    )
    expected_names = [c.name for c in outcome.expected_calls]

    if outcome.should_call:
        name_score = _jaccard(outcome.predicted_names, expected_names)
        if outcome.expected_calls:
            arg_scores = [
                _arg_score(outcome.predicted_args_by_name.get(exp.name, {}), exp)
                for exp in outcome.expected_calls
            ]
            arg_score = sum(arg_scores) / len(arg_scores)
        else:
            arg_score = 1.0
    else:
        # no-tool case: name/arg score reflects whether nothing was called.
        name_score = 1.0 if predicted_count == 0 else 0.0
        arg_score = 1.0 if predicted_count == 0 else 0.0

    exact = decision_correct and name_score >= 1.0 and arg_score >= 1.0
    return CaseMetric(
        case_id=outcome.case_id,
        category=outcome.category,
        decision_correct=decision_correct,
        name_score=name_score,
        arg_score=arg_score,
        exact=exact,
        false_positive=(not outcome.should_call) and predicted_count > 0,
        false_negative=outcome.should_call and predicted_count == 0,
        parse_ok=outcome.parse_ok,
        tool_count=predicted_count,
    )


def compute_metrics(outcomes: list[CaseOutcome]) -> dict[str, float]:
    """Aggregate the 8 metrics over a list of case outcomes."""
    if not outcomes:
        return {k: 0.0 for k in METRIC_KEYS}

    metrics_list = [score_case(o) for o in outcomes]
    n = len(metrics_list)
    tool_outcomes = [o for o in outcomes if o.should_call]
    no_tool_outcomes = [o for o in outcomes if not o.should_call]
    should_call_metrics = [
        m for m, o in zip(metrics_list, outcomes, strict=False) if o.should_call
    ]

    decision_accuracy = sum(m.decision_correct for m in metrics_list) / n
    if should_call_metrics:
        tool_name_accuracy = sum(m.name_score for m in should_call_metrics) / len(
            should_call_metrics
        )
        argument_accuracy = sum(m.arg_score for m in should_call_metrics) / len(
            should_call_metrics
        )
    else:
        tool_name_accuracy = 1.0
        argument_accuracy = 1.0
    exact_match = sum(m.exact for m in metrics_list) / n
    false_positive_rate = (
        sum(m.false_positive for m in metrics_list) / len(no_tool_outcomes)
        if no_tool_outcomes
        else 0.0
    )
    false_negative_rate = (
        sum(m.false_negative for m in metrics_list) / len(tool_outcomes)
        if tool_outcomes
        else 0.0
    )
    parse_success_rate = sum(m.parse_ok for m in metrics_list) / n
    avg_tool_count = sum(m.tool_count for m in metrics_list) / n

    return {
        "decision_accuracy": round(decision_accuracy, 4),
        "tool_name_accuracy": round(tool_name_accuracy, 4),
        "argument_accuracy": round(argument_accuracy, 4),
        "exact_match": round(exact_match, 4),
        "false_positive_rate": round(false_positive_rate, 4),
        "false_negative_rate": round(false_negative_rate, 4),
        "parse_success_rate": round(parse_success_rate, 4),
        "avg_tool_count": round(avg_tool_count, 4),
    }


def compute_metrics_by_category(
    outcomes: list[CaseOutcome],
) -> dict[str, dict[str, float]]:
    """Per-category breakdown keyed by category name."""
    by_cat: dict[str, list[CaseOutcome]] = {}
    for o in outcomes:
        by_cat.setdefault(o.category, []).append(o)
    return {cat: compute_metrics(items) for cat, items in by_cat.items()}


def outcome_from_case(
    case: dict[str, Any],
    predicted_calls: list[Any],
    parse_ok: bool = True,
) -> CaseOutcome:
    """Build a :class:`CaseOutcome` from a raw case dict + predicted calls.

    ``predicted_calls`` items may be :class:`ToolCallResult` or any object with
    ``.name`` / ``.args`` (or a dict with ``name``/``args`` keys).
    """
    exp = case["expected"]
    expected_calls = [
        ExpectedCall(
            name=tc["name"],
            args_match=dict(tc.get("args_match", {})),
            args_required=list(tc.get("args_required", [])),
        )
        for tc in exp.get("expected_tool_calls", [])
    ]

    predicted_names: list[str] = []
    predicted_args_by_name: dict[str, dict[str, Any]] = {}
    for call in predicted_calls:
        if isinstance(call, dict):
            name = call.get("name", "")
            args = dict(call.get("args", {}))
        else:
            name = getattr(call, "name", "")
            args = dict(getattr(call, "args", {}))
        if not name:
            continue
        predicted_names.append(name)
        if name not in predicted_args_by_name:
            predicted_args_by_name[name] = args

    return CaseOutcome(
        case_id=case["case_id"],
        category=case["category"],
        should_call=bool(exp["should_call_tool"]),
        expected_calls=expected_calls,
        predicted_names=predicted_names,
        predicted_args_by_name=predicted_args_by_name,
        parse_ok=parse_ok,
    )


__all__ = [
    "METRIC_KEYS",
    "CaseMetric",
    "CaseOutcome",
    "ExpectedCall",
    "compute_metrics",
    "compute_metrics_by_category",
    "outcome_from_case",
    "score_case",
]
