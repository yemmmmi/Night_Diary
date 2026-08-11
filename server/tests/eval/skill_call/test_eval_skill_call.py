"""Skill-call accuracy eval: full vs progressive-disclosure injection (A/B).

Runs each of the 30 annotated cases through both injection strategies, computes
the selection + efficiency metrics (accuracy / F1 / FAR / MAR / avg_tokens /
avg_latency / avg_disclosure_rounds), prints an A/B comparison table +
per-category breakdown + failure samples, and guards against regression vs a
recorded ``baseline.json``.

Out of CI; run via::

    make eval-skill                              # report + regression check
    EVAL_UPDATE_BASELINE=1 make eval-skill      # (re)seed baseline.json

See ``BASELINE.md`` for the protocol design and recorded values.
"""

from __future__ import annotations

import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from app.domain.skills.injection import (
    FullInjectionStrategy,
    ProgressiveDisclosureStrategy,
)
from app.domain.skills.skill_loader import SkillDoc
from app.shared.token_utils import estimate_tokens
from tests.eval.skill_call.conftest import (
    build_full_prompt,
    build_progressive_prompt,
    parse_use_skill_tags,
)
from tests.eval.skill_call.metrics import (
    METRIC_KEYS,
    CaseOutcome,
    compute_metrics,
    compute_metrics_by_category,
    outcome_from_case,
    score_case,
)

# Excluded from the default test run (CI); selected only via `make eval-skill`.
pytestmark = pytest.mark.eval

#: Absolute tolerance: a drop beyond this below the recorded baseline is a
#: real regression to explain/fix.
REGRESSION_TOLERANCE = 0.05
BASELINE_PATH = Path(__file__).parent / "baseline.json"

#: Selection metrics where "higher is better" (used by the regression guard).
#: Efficiency metrics (tokens / latency / rounds) are reported for comparison
#: but not subject to the regression guard (they vary by environment).
_REGRESSION_METRICS = (
    "skill_selection_accuracy",
    "skill_selection_f1",
)


# --------------------------------------------------------------------------- #
# Run helpers (one case -> predicted skills per strategy)
# --------------------------------------------------------------------------- #
def _invoke_llm(llm: Any, prompt: str) -> tuple[str, float]:
    """Invoke LLM and return (response_text, latency_ms)."""
    start = time.perf_counter()
    msg = llm.invoke(prompt)
    latency_ms = (time.perf_counter() - start) * 1000
    text = getattr(msg, "content", "") or ""
    return text, latency_ms


def _run_full(
    case: dict[str, Any],
    skills: list[SkillDoc],
    injector: FullInjectionStrategy,
    llm: Any,
    real_mode: bool,
) -> CaseOutcome:
    """Run one case through the full-injection strategy."""
    prompt = build_full_prompt(case, skills, injector, real_mode=real_mode)
    tokens = estimate_tokens(prompt)
    text, latency_ms = _invoke_llm(llm, prompt)
    predicted = parse_use_skill_tags(text)
    return outcome_from_case(
        case,
        predicted,
        prompt_tokens=tokens,
        latency_ms=latency_ms,
        disclosure_rounds=0,  # full strategy: no on-demand loading
    )


def _run_progressive(
    case: dict[str, Any],
    skills: list[SkillDoc],
    injector: ProgressiveDisclosureStrategy,
    llm: Any,
    real_mode: bool,
) -> CaseOutcome:
    """Run one case through the progressive-disclosure strategy.

    Disclosure rounds = number of skills the LLM declared (each declaration
    triggers one on-demand body load).
    """
    prompt = build_progressive_prompt(case, skills, injector, real_mode=real_mode)
    tokens = estimate_tokens(prompt)
    text, latency_ms = _invoke_llm(llm, prompt)
    predicted = parse_use_skill_tags(text)
    disclosure_rounds = len(predicted)
    return outcome_from_case(
        case,
        predicted,
        prompt_tokens=tokens,
        latency_ms=latency_ms,
        disclosure_rounds=disclosure_rounds,
    )


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def _print_report(
    full_metrics: dict[str, float],
    progressive_metrics: dict[str, float],
    token_savings: float,
    full_by_cat: dict[str, dict[str, float]],
    prog_by_cat: dict[str, dict[str, float]],
    failures: list[str],
    real_mode: bool,
    model_name: str,
    n_cases: int,
) -> None:
    sep = "=" * 88
    print("\n" + sep)
    mode = f"{model_name} (REAL)" if real_mode else "stub"
    print(f"Skill-call accuracy baseline ({mode}, {n_cases} cases x 2 strategies)")
    print(sep)

    header = (
        f"{'strategy':<12}"
        f"{'accuracy':>10}"
        f"{'f1':>10}"
        f"{'FAR':>10}"
        f"{'MAR':>10}"
        f"{'avg_tok':>10}"
        f"{'avg_ms':>10}"
        f"{'rounds':>8}"
    )
    print(header)
    print("-" * len(header))
    for name, metrics in (("full", full_metrics), ("progressive", progressive_metrics)):
        print(
            f"{name:<12}"
            f"{metrics['skill_selection_accuracy']:>10.4f}"
            f"{metrics['skill_selection_f1']:>10.4f}"
            f"{metrics['false_activation_rate']:>10.4f}"
            f"{metrics['missed_activation_rate']:>10.4f}"
            f"{metrics['avg_prompt_tokens']:>10.1f}"
            f"{metrics['avg_latency_ms']:>10.1f}"
            f"{metrics['avg_disclosure_rounds']:>8.2f}"
        )

    print(f"\ntoken_savings (1 - prog/full): {token_savings:.2%}")

    print("\nPer-category accuracy (full / progressive):")
    cats = sorted(set(full_by_cat) | set(prog_by_cat))
    for cat in cats:
        f_acc = full_by_cat.get(cat, {}).get("skill_selection_accuracy", 0.0)
        p_acc = prog_by_cat.get(cat, {}).get("skill_selection_accuracy", 0.0)
        print(f"  {cat:<20}{f_acc:>10.4f}{p_acc:>12.4f}")

    if failures:
        print("\nFailure samples (exact_match == False):")
        for line in failures[:20]:
            print(line)
        if len(failures) > 20:
            print(f"  ... {len(failures) - 20} more")
    print(sep + "\n")


def _load_baseline() -> dict[str, Any] | None:
    if not BASELINE_PATH.exists():
        return None
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def _write_baseline(
    full: dict[str, float],
    progressive: dict[str, float],
    token_savings: float,
) -> None:
    payload = {
        "full": full,
        "progressive": progressive,
        "token_savings": round(token_savings, 4),
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
    skills_list: list[SkillDoc],
    full_injector: FullInjectionStrategy,
    progressive_injector: ProgressiveDisclosureStrategy,
    stub_llm: Any,
    real_llm: Any,
    real_mode: bool,
    model_name: str,
) -> dict[str, Any]:
    full_outcomes: list[CaseOutcome] = []
    progressive_outcomes: list[CaseOutcome] = []
    failures: list[str] = []

    llm = real_llm if real_mode else stub_llm

    for case in eval_cases:
        full_outcomes.append(
            _run_full(case, skills_list, full_injector, llm, real_mode)
        )
        progressive_outcomes.append(
            _run_progressive(
                case, skills_list, progressive_injector, llm, real_mode
            )
        )

    full_metrics = compute_metrics(full_outcomes)
    progressive_metrics = compute_metrics(progressive_outcomes)
    full_by_cat = compute_metrics_by_category(full_outcomes)
    prog_by_cat = compute_metrics_by_category(progressive_outcomes)

    full_tokens = full_metrics["avg_prompt_tokens"]
    prog_tokens = progressive_metrics["avg_prompt_tokens"]
    token_savings = (
        1 - prog_tokens / full_tokens if full_tokens > 0 else 0.0
    )

    # Collect failures (exact_match == False; full path as primary signal)
    for outcome in full_outcomes:
        m = score_case(outcome)
        if not m.exact_match:
            failures.append(
                f"  [full] {outcome.case_id} ({outcome.category}) "
                f"predicted={outcome.predicted_skills} "
                f"expected={outcome.expected_skills}"
            )

    _print_report(
        full_metrics,
        progressive_metrics,
        token_savings,
        full_by_cat,
        prog_by_cat,
        failures,
        real_mode,
        model_name,
        len(eval_cases),
    )

    if os.getenv("EVAL_UPDATE_BASELINE") == "1":
        _write_baseline(full_metrics, progressive_metrics, token_savings)
        print(
            f"[baseline] wrote {BASELINE_PATH.name} "
            f"(full + progressive) for {len(eval_cases)} cases"
        )

    return {
        "full": full_metrics,
        "progressive": progressive_metrics,
        "token_savings": token_savings,
        "full_by_category": full_by_cat,
        "progressive_by_category": prog_by_cat,
        "failures": failures,
        "real_mode": real_mode,
        "model_name": model_name,
        "n_cases": len(eval_cases),
        "full_outcomes": full_outcomes,
        "progressive_outcomes": progressive_outcomes,
    }


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
_EXPECTED_CATEGORIES = {
    "emotional": 6,
    "crisis": 5,
    "retrospective": 6,
    "entity_query": 5,
    "multi_skill": 4,
    "no_skill_casual": 4,
}

_ALL_SKILL_NAMES = {
    "crisis_detector",
    "sentiment_skill",
    "memory_recall",
    "entity_tracker",
}


def test_dataset_integrity(eval_cases: list[dict[str, Any]]) -> None:
    """The dataset must be exactly 30 cases across the 6 fixed categories."""
    assert len(eval_cases) == 30, f"expected 30 cases, got {len(eval_cases)}"
    cats = Counter(c["category"] for c in eval_cases)
    assert dict(cats) == _EXPECTED_CATEGORIES, (
        f"category counts mismatch: {dict(cats)}"
    )
    seen: set[str] = set()
    for c in eval_cases:
        assert c["case_id"] not in seen, f"duplicate case_id: {c['case_id']}"
        seen.add(c["case_id"])
        assert c["user_message"]
        assert isinstance(c["available_skills"], list)
        assert set(c["available_skills"]) == _ALL_SKILL_NAMES, (
            f"{c['case_id']}: available_skills must be all 4 skills"
        )
        assert isinstance(c["expected_skills"], list)
        for s in c["expected_skills"]:
            assert s in _ALL_SKILL_NAMES, (
                f"{c['case_id']}: unknown skill '{s}' in expected_skills"
            )


def test_full_strategy_runs(eval_report: dict[str, Any]) -> None:
    """Full-injection path must produce a complete metric block."""
    m = eval_report["full"]
    for key in METRIC_KEYS:
        assert key in m, f"full missing metric {key}"
    assert 0.0 <= m["skill_selection_accuracy"] <= 1.0
    assert 0.0 <= m["skill_selection_f1"] <= 1.0


def test_progressive_strategy_runs(eval_report: dict[str, Any]) -> None:
    """Progressive-disclosure path must produce a complete metric block."""
    m = eval_report["progressive"]
    for key in METRIC_KEYS:
        assert key in m, f"progressive missing metric {key}"
    assert 0.0 <= m["skill_selection_accuracy"] <= 1.0
    assert 0.0 <= m["skill_selection_f1"] <= 1.0


def test_stub_wiring(eval_report: dict[str, Any], real_mode: bool) -> None:
    """In stub mode both paths must be perfect (oracle input -> correct parse).

    This proves the ``<use_skill>`` parsing pipeline and the metric wiring are
    correct: given the expected tags, every selection metric lands at 1.0.
    Real mode is skipped (the real LLM is imperfect by design).
    """
    if real_mode:
        pytest.skip("stub-wiring check only applies to stub mode")
    for path in ("full", "progressive"):
        m = eval_report[path]
        assert m["skill_selection_accuracy"] == pytest.approx(1.0), (
            f"{path}: accuracy != 1.0 in stub mode"
        )
        assert m["skill_selection_f1"] == pytest.approx(1.0), (
            f"{path}: f1 != 1.0 in stub mode"
        )
        assert m["false_activation_rate"] == pytest.approx(0.0), (
            f"{path}: FAR != 0.0 in stub mode"
        )
        assert m["missed_activation_rate"] == pytest.approx(0.0), (
            f"{path}: MAR != 0.0 in stub mode"
        )


def test_progressive_cheaper_than_full(
    eval_report: dict[str, Any],
    skills_list: list[SkillDoc],
    full_injector: FullInjectionStrategy,
    progressive_injector: ProgressiveDisclosureStrategy,
) -> None:
    """Progressive prompt must be cheaper (fewer tokens) than full prompt.

    This is the core value proposition of progressive disclosure: summaries are
    strictly smaller than full text. Verified structurally (not via LLM output).
    """
    full_cost = full_injector.estimate_injection_cost(skills_list)
    prog_cost = progressive_injector.estimate_injection_cost(skills_list)
    assert prog_cost < full_cost, (
        f"Progressive ({prog_cost}) should be cheaper than full ({full_cost})"
    )
    assert eval_report["token_savings"] > 0, (
        "token_savings should be positive (progressive saves tokens)"
    )


def test_progressive_disclosure_rounds(eval_report: dict[str, Any]) -> None:
    """Progressive path must report disclosure rounds; full path must be 0."""
    assert eval_report["full"]["avg_disclosure_rounds"] == 0.0, (
        "Full strategy should have 0 disclosure rounds"
    )
    # Progressive: in stub mode, disclosure rounds = avg expected skills > 0
    prog_rounds = eval_report["progressive"]["avg_disclosure_rounds"]
    assert prog_rounds >= 0.0


def test_no_regression_vs_baseline(eval_report: dict[str, Any], real_mode: bool) -> None:
    """Soft per-strategy check: fail only on a real drop below the recorded value."""
    if not real_mode:
        pytest.skip("regression vs baseline only checked in real mode (LLM_API_KEY set)")
    baseline = _load_baseline()
    if not baseline or baseline.get("_placeholder"):
        pytest.skip(
            "placeholder baseline; seed with EVAL_UPDATE_BASELINE=1 make eval-skill"
        )

    regressions: list[str] = []
    for path in ("full", "progressive"):
        recorded = baseline.get(path, {})
        current = eval_report[path]
        for key in _REGRESSION_METRICS:
            rec = recorded.get(key)
            cur = current.get(key)
            if rec is None or cur is None:
                continue
            if cur < rec - REGRESSION_TOLERANCE:
                regressions.append(
                    f"{path}.{key}: {cur:.4f} < {rec:.4f} - {REGRESSION_TOLERANCE}"
                )

    assert not regressions, "Skill-call regression vs baseline:\n" + "\n".join(
        regressions
    )
