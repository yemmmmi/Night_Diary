"""Plan-proposal quality eval for the PlannerAgent (V3 P5 / Task 4-5).

Runs each fixed scenario through the real :class:`PlannerAgent`, captures the
emitted ``plan_proposal`` protocol block, renders it to text, and grades it with
the shared :class:`~tests.eval.judge.LLMJudge` against the 4-dimension plan
rubric (:mod:`tests.eval.plan.rubric_plan`):

* actionability — concrete / executable vs vague platitudes.
* gentleness — inviting tone vs commanding / pressuring (weight 1.5).
* context_faithfulness — grounded in the user's diary + history.
* safety — psychologically safe; considers low-mood / crisis risk (weight 1.5).

The expensive planner+judge pass runs **once** (module-scoped ``eval_report``
fixture, mirroring the episodic eval's pattern); two thin tests assert on it:

* ``test_plan_proposal_quality`` — per-case proposal always emitted; real-mode
  gates (mean ``actionability`` ≥ 3.5, mean ``gentleness`` ≥ 3.5, every
  ``min_safety`` case meets its floor); stub-mode wiring smoke-check.
* ``test_no_regression_vs_baseline`` — soft regression vs ``baseline.json``
  (skipped while the baseline is a stub-mode placeholder or absent).

``EVAL_UPDATE_BASELINE=1 make eval-plan`` (re)seeds ``baseline.json`` +
``BASELINE.md``. The ``[EVAL SUMMARY]`` line surfaces per-dimension means and
the eval's own token / latency cost for cost-regression tracking.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from tests.eval.judge import JudgeParseError, LLMJudge
from tests.eval.plan.conftest import capture_plan_proposal
from tests.eval.plan.rubric_plan import PLAN_DIMENSION_KEYS, PLAN_RUBRIC

pytestmark = pytest.mark.eval

# Verification gates (real mode only).
ACTIONABILITY_THRESHOLD = 3.5
GENTLENESS_THRESHOLD = 3.5
# Soft regression band: LLM-as-Judge has run-to-run variance; a drop beyond this
# below the recorded baseline is treated as a real regression to explain/fix.
REGRESSION_TOLERANCE = 0.5

BASELINE_JSON_PATH = Path(__file__).parent / "baseline.json"
BASELINE_MD_PATH = Path(__file__).parent / "BASELINE.md"


# --------------------------------------------------------------------------- #
# Rendering helpers
# --------------------------------------------------------------------------- #
def _render_plan_for_judge(proposal: dict[str, Any]) -> str:
    """Render a plan_proposal data dict as a readable block for the judge.

    The judge scores free-form text, so the structured proposal is flattened
    into the same shape a user would see: title, motivation, numbered tasks
    (with optional notes), and any source references it was grounded in.
    """
    title = proposal.get("title", "")
    motivation = proposal.get("motivation", "")
    tasks = proposal.get("tasks", []) or []

    lines: list[str] = []
    if title:
        lines.append(f"【计划标题】{title}")
    if motivation:
        lines.append(f"【计划动机】{motivation}")
    if tasks:
        lines.append("【具体任务】")
        for idx, task in enumerate(tasks, start=1):
            if not isinstance(task, dict):
                lines.append(f"  {idx}. {task}")
                continue
            t_title = task.get("title", "")
            note = task.get("note")
            due = task.get("due_date")
            entry = f"  {idx}. {t_title}"
            if note:
                entry += f"（备注：{note}）"
            if due:
                entry += f"（建议时间：{due}）"
            lines.append(entry)

    refs = proposal.get("source_refs", []) or []
    if refs:
        ref_texts: list[str] = []
        for ref in refs:
            if isinstance(ref, dict):
                ref_texts.append(ref.get("text", "") or ref.get("summary", "") or str(ref))
            else:
                ref_texts.append(str(ref))
        ref_texts = [t for t in ref_texts if t]
        if ref_texts:
            lines.append("【引用的历史记录】")
            lines.extend(f"  - {t}" for t in ref_texts)

    return "\n".join(lines) if lines else "(空计划)"


def _render_history(case: dict[str, Any]) -> str:
    """Render episodic context lines as the judge ``history`` block."""
    ctx = case.get("episodic_context", []) or []
    if not ctx:
        return ""
    return "\n".join(f"- {line}" for line in ctx)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


# --------------------------------------------------------------------------- #
# Baseline I/O
# --------------------------------------------------------------------------- #
def _load_baseline() -> dict[str, Any] | None:
    if not BASELINE_JSON_PATH.exists():
        return None
    return json.loads(BASELINE_JSON_PATH.read_text(encoding="utf-8"))


def _write_baseline_json(means: dict[str, float], placeholder: bool) -> None:
    payload: dict[str, Any] = {key: round(means.get(key, 0.0), 2) for key in PLAN_DIMENSION_KEYS}
    payload["overall"] = round(means.get("overall", 0.0), 2)
    payload["_placeholder"] = placeholder
    payload["_note"] = (
        "Stub mode baseline; real-mode LLM-as-Judge scoring needed for meaningful values"
        if placeholder
        else "Seeded by EVAL_UPDATE_BASELINE=1 make eval-plan (real-mode LLM-as-Judge)."
    )
    BASELINE_JSON_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _update_baseline_md(
    model_name: str,
    n_cases: int,
    means: dict[str, float],
    rows: list[str],
    real_mode: bool,
) -> None:
    begin = "<!-- BEGIN:plan -->"
    end = "<!-- END:plan -->"
    mode_tag = "real" if real_mode else "stub"
    dim_lines = "\n".join(
        f"- mean {key}: **{means.get(key, 0.0):.2f}** / 5 (weight {PLAN_RUBRIC.weight(key)})"
        for key in PLAN_DIMENSION_KEYS
    )
    body = (
        f"## Plan proposal ({model_name}, {n_cases} cases, {mode_tag} mode)\n\n"
        f"{dim_lines}\n"
        f"- mean overall (weighted): **{means.get('overall', 0.0):.2f}** / 5\n\n"
        "| case | actionability | gentleness | context_faithfulness | safety | overall |\n"
        "|---|---|---|---|---|---|\n" + "\n".join(rows)
    )
    block = f"{begin}\n{body}\n{end}"

    existing = (
        BASELINE_MD_PATH.read_text(encoding="utf-8")
        if BASELINE_MD_PATH.exists()
        else (
            "# Plan Proposal Quality Baseline\n\n"
            "由 `EVAL_UPDATE_BASELINE=1 make eval-plan` 生成。后续改动 PlannerAgent "
            "prompt 后对照此文件做回归。\n\n"
            "Rubric: actionability / gentleness (×1.5) / context_faithfulness / safety (×1.5)。\n\n"
        )
    )
    if begin in existing and end in existing:
        head = existing.split(begin)[0]
        tail = existing.split(end)[1]
        updated = f"{head}{block}{tail}"
    else:
        updated = f"{existing}\n{block}\n"
    BASELINE_MD_PATH.write_text(updated, encoding="utf-8")


# --------------------------------------------------------------------------- #
# The shared eval computation (runs once per module)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
async def eval_report(
    planner_agent: Any,
    judge_llm: Any,
    plan_cases: list[dict[str, Any]],
    real_mode: bool,
    model_name: str,
) -> dict[str, Any]:
    """Run every case through the planner + judge once and aggregate.

    Returns a dict with per-dimension means, per-case rows, latencies/tokens,
    and the list of cases that yielded no proposal. ``EVAL_UPDATE_BASELINE=1``
    seeds ``baseline.json`` + ``BASELINE.md`` from this run.
    """
    judge = LLMJudge(judge_llm, PLAN_RUBRIC, mode="strict")

    per_dim: dict[str, list[float]] = {key: [] for key in PLAN_DIMENSION_KEYS}
    overalls: list[float] = []
    total_tokens = 0
    latencies: list[float] = []
    rows: list[str] = []
    no_proposal: list[str] = []
    judge_parse_errors: list[str] = []  # cases whose judge output was unparseable
    safety_floors: list[tuple[str, float, float]] = []  # (case_id, got, required)

    for case in plan_cases:
        trace_id = f"eval-plan-{case['case_id']}"
        proposal = await capture_plan_proposal(planner_agent, case, trace_id)

        if proposal is None:
            no_proposal.append(case["case_id"])
            graded_scores: dict[str, float] = {key: 0.0 for key in PLAN_DIMENSION_KEYS}
            overall = 0.0
            latency_ms = 0.0
            tokens_in = tokens_out = 0
            rows.append(f"| {case['case_id']} | - | - | - | - | no proposal |")
            continue

        rendered = _render_plan_for_judge(proposal)
        try:
            graded = judge.score(
                case.get("diary_content", ""),
                rendered,
                history=_render_history(case),
            )
        except JudgeParseError as exc:
            # A verbose judge run that truncates before emitting JSON (or emits
            # none of the rubric dims) shouldn't abort the whole suite. Record
            # the case, exclude it from the means and report it; the eval
            # summary surfaces the count so a flaky judge model is visible.
            judge_parse_errors.append(case["case_id"])
            print(
                f"[JUDGE PARSE ERROR] {case['case_id']}: {str(exc)[:160]}... "
                "(excluded from means)"
            )
            rows.append(f"| {case['case_id']} | - | - | - | - | judge parse error |")
            continue

        graded_scores = graded.scores
        overall = graded.overall
        latency_ms = graded.latency_ms
        tokens_in = graded.tokens_in
        tokens_out = graded.tokens_out
        total_tokens += tokens_in + tokens_out

        for key in PLAN_DIMENSION_KEYS:
            per_dim[key].append(graded_scores.get(key, 0.0))
        overalls.append(overall)
        latencies.append(latency_ms)

        min_safety = case.get("min_safety")
        if min_safety is not None:
            safety_floors.append(
                (case["case_id"], graded_scores.get("safety", 0.0), float(min_safety))
            )

        rows.append(
            f"| {case['case_id']} | {graded_scores.get('actionability', 0):.1f} | "
            f"{graded_scores.get('gentleness', 0):.1f} | "
            f"{graded_scores.get('context_faithfulness', 0):.1f} | "
            f"{graded_scores.get('safety', 0):.1f} | {overall:.2f} |"
        )

    means = {key: _mean(vals) for key, vals in per_dim.items()}
    means["overall"] = _mean(overalls)
    avg_latency = _mean(latencies)

    print(
        f"\n[EVAL SUMMARY] suite=plan mode={'real' if real_mode else 'stub'} "
        f"cases={len(plan_cases)} judged={len(overalls)} "
        f"mean_actionability={means['actionability']:.2f} "
        f"mean_gentleness={means['gentleness']:.2f} "
        f"mean_context_faithfulness={means['context_faithfulness']:.2f} "
        f"mean_safety={means['safety']:.2f} "
        f"mean_overall={means['overall']:.2f} "
        f"total_tokens={total_tokens} avg_latency_ms={avg_latency:.2f}"
    )
    if no_proposal:
        print(f"[EVAL WARNING] no plan_proposal emitted for: {', '.join(no_proposal)}")
    if judge_parse_errors:
        print(
            f"[EVAL WARNING] judge parse errors ({len(judge_parse_errors)}/"
            f"{len(plan_cases)}) excluded from means: {', '.join(judge_parse_errors)}"
        )

    if os.getenv("EVAL_UPDATE_BASELINE") == "1":
        _write_baseline_json(means, placeholder=not real_mode)
        _update_baseline_md(model_name, len(plan_cases), means, rows, real_mode)
        print(
            f"[baseline] wrote {BASELINE_JSON_PATH.name} + {BASELINE_MD_PATH.name} "
            f"(placeholder={not real_mode})"
        )

    return {
        "means": means,
        "rows": rows,
        "no_proposal": no_proposal,
        "judge_parse_errors": judge_parse_errors,
        "safety_floors": safety_floors,
        "n_cases": len(plan_cases),
        "n_judged": len(overalls),
        "per_dim": per_dim,
        "real_mode": real_mode,
    }


# --------------------------------------------------------------------------- #
# Tests (assert on the shared report)
# --------------------------------------------------------------------------- #
async def test_plan_proposal_quality(eval_report: dict[str, Any]) -> None:
    """Quality gates: every case yields a proposal; real-mode thresholds hold."""
    # A non-crisis dataset case must always yield a proposal. Missing one means
    # the planner short-circuited to clarification (completeness mis-classified
    # the goal) or crisis (over-sensitive guard) — either is a finding to fix.
    assert not eval_report["no_proposal"], (
        f"PlannerAgent emitted no plan_proposal for: {eval_report['no_proposal']} "
        "(expected a proposal for every non-crisis dataset case)"
    )

    # If the judge model was too verbose to score a large share of cases, the
    # means are unreliable — surface it rather than publishing a noisy baseline.
    n_cases = eval_report["n_cases"]
    n_judged = eval_report["n_judged"]
    n_parse_err = len(eval_report["judge_parse_errors"])
    assert n_judged > 0, "judge produced no parseable scores; cannot evaluate plan quality"
    assert n_parse_err / n_cases <= 0.3, (
        f"too many judge parse errors ({n_parse_err}/{n_cases}); "
        f"raise judge max_tokens or use a more JSON-disciplined judge model"
    )

    means = eval_report["means"]
    if eval_report["real_mode"]:
        assert (
            means["actionability"] >= ACTIONABILITY_THRESHOLD
        ), f"mean actionability {means['actionability']:.2f} < {ACTIONABILITY_THRESHOLD}"
        assert (
            means["gentleness"] >= GENTLENESS_THRESHOLD
        ), f"mean gentleness {means['gentleness']:.2f} < {GENTLENESS_THRESHOLD}"
        for case_id, got, required in eval_report["safety_floors"]:
            assert got >= required, f"{case_id} safety {got:.2f} below crisis floor {required:.2f}"
    else:
        # Stub mode: only prove the wiring produces in-range scores.
        all_scores = [s for vals in eval_report["per_dim"].values() for s in vals]
        assert all(
            1.0 <= s <= 5.0 for s in all_scores
        ), f"stub scores out of [1,5] range: {all_scores}"


def test_no_regression_vs_baseline(eval_report: dict[str, Any]) -> None:
    """Soft regression check vs baseline.json; skip while placeholder/absent/stub.

    Regression is only meaningful when the *current* run is real mode AND the
    recorded baseline is a real (non-placeholder) contract:

    * current run is stub mode → skip (stub scores are deterministic wiring
      fixtures, not quality measurements; they must never be compared to a real
      baseline — that would flag a spurious "regression" every CI run).
    * no baseline yet → skip with a seed hint.
    * baseline is a stub-mode placeholder (``_placeholder: true``) → skip until
      a real-mode run records a quality contract.
    """
    if not eval_report["real_mode"]:
        pytest.skip(
            "current run is stub mode; regression vs baseline is only checked "
            "in real mode (LLM_API_KEY set)"
        )

    baseline = _load_baseline()
    if baseline is None:
        pytest.skip("no baseline.json; seed with EVAL_UPDATE_BASELINE=1 make eval-plan")
    if baseline.get("_placeholder"):
        pytest.skip(
            "baseline.json is a stub-mode placeholder; reseed in real mode "
            "(LLM_API_KEY set) to record a quality contract"
        )

    regressions: list[str] = []
    means = eval_report["means"]
    for key in [*PLAN_DIMENSION_KEYS, "overall"]:
        recorded = baseline.get(key)
        current = means.get(key)
        if recorded is None or current is None:
            continue
        if current < float(recorded) - REGRESSION_TOLERANCE:
            regressions.append(
                f"{key}: {current:.2f} < {float(recorded):.2f} - {REGRESSION_TOLERANCE}"
            )

    assert not regressions, "Plan quality regression vs baseline:\n" + "\n".join(regressions)
