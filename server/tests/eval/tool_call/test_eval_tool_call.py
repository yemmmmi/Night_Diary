"""Tool-call accuracy eval: native vs fallback protocol paths.

Runs each of the 40 annotated cases through both protocol paths, computes the
8 metrics (decision / tool-name / argument / exact / FPR / FNR /
parse-success / avg-tool-count), prints a comparison table + per-category
breakdown + failure samples, and guards against regression vs a recorded
``baseline.json``.

Out of CI; run via::

    make eval-tool                              # report + regression check
    EVAL_UPDATE_BASELINE=1 make eval-tool       # (re)seed baseline.json

See ``BASELINE.md`` for the protocol design and recorded values.
"""

from __future__ import annotations

import contextlib
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from app.services.ai.tool_factory import specs_for_names
from app.shared.tool_protocol import (
    TOOL_CALL_PATTERN,
    build_tool_hint,
    extract_native_tool_calls,
    parse_text_tag_calls,
)
from tests.eval.tool_call.conftest import RecordingTool, _stub_key
from tests.eval.tool_call.metrics import (
    METRIC_KEYS,
    compute_metrics,
    compute_metrics_by_category,
    outcome_from_case,
    score_case,
)

# Excluded from the default test run (CI); selected only via `make eval-tool`.
pytestmark = pytest.mark.eval

#: Absolute tolerance: a drop beyond this below the recorded baseline is a
#: real regression to explain/fix. Small-sample fluctuation is allowed.
REGRESSION_TOLERANCE = 0.05
BASELINE_PATH = Path(__file__).parent / "baseline.json"

#: Metrics where "higher is better" (used by the regression guard).
#: ``avg_tool_count`` is a count, not accuracy — excluded from regression.
_REGRESSION_METRICS = tuple(k for k in METRIC_KEYS if k != "avg_tool_count")


# --------------------------------------------------------------------------- #
# Run helpers (one case -> predicted tool calls per path)
# --------------------------------------------------------------------------- #
def _native_prompt(case: dict[str, Any], real_mode: bool) -> str:
    """Real mode: send the raw user message. Stub mode: prefix case_id."""
    if real_mode:
        return case["user_message"]
    return f"{_stub_key(case['case_id'])} {case['user_message']}"


def _fallback_prompt(case: dict[str, Any]) -> str:
    """Always prefix case_id (stub match) + append the text-tag hint."""
    enabled = specs_for_names(case["enabled_tools"])
    hint = build_tool_hint(enabled)
    return f"{_stub_key(case['case_id'])} {case['user_message']}{hint}"


def _check_parse_ok(text: str) -> bool:
    """True when every ``<args>`` block is valid JSON (no raw-string fallback)."""
    for match in TOOL_CALL_PATTERN.finditer(text):
        raw = match.group(2).strip()
        if not raw:
            continue  # empty -> parses to {}
        try:
            json.loads(raw)
        except (ValueError, TypeError):
            return False
    return True


def _record_executions(
    calls: list[Any], recording_tools: dict[str, RecordingTool]
) -> None:
    """Execute predicted calls through the recording wrappers (best-effort)."""
    for call in calls:
        name = getattr(call, "name", "") or (call.get("name", "") if isinstance(call, dict) else "")
        tool = recording_tools.get(name)
        if tool is None:
            continue
        args = (
            dict(getattr(call, "args", {}))
            if not isinstance(call, dict)
            else dict(call.get("args", {}))
        )
        with contextlib.suppress(Exception):
            tool(**args)


def _run_native(
    case: dict[str, Any],
    native_llm: Any,
    real_mode: bool,
    recording_tools: dict[str, RecordingTool],
) -> tuple[list[Any], bool]:
    enabled = specs_for_names(case["enabled_tools"])
    bound = native_llm.bind_tools(enabled)
    prompt = _native_prompt(case, real_mode)
    try:
        msg = bound.invoke(prompt)
        calls = extract_native_tool_calls(msg)
        parse_ok = True
    except Exception:
        calls, parse_ok = [], False
    _record_executions(calls, recording_tools)
    return calls, parse_ok


def _run_fallback(
    case: dict[str, Any],
    fallback_llm: Any,
    recording_tools: dict[str, RecordingTool],
) -> tuple[list[Any], bool]:
    prompt = _fallback_prompt(case)
    msg = fallback_llm.invoke(prompt)
    text = getattr(msg, "content", "") or ""
    calls = parse_text_tag_calls(text)
    parse_ok = _check_parse_ok(text)
    _record_executions(calls, recording_tools)
    return calls, parse_ok


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def _print_report(
    native_metrics: dict[str, float],
    fallback_metrics: dict[str, float],
    native_by_cat: dict[str, dict[str, float]],
    fallback_by_cat: dict[str, dict[str, float]],
    failures: list[str],
    native_exec: int,
    fallback_exec: int,
    real_mode: bool,
    model_name: str,
    n_cases: int,
) -> None:
    sep = "=" * 80
    print("\n" + sep)
    mode = f"{model_name} (REAL)" if real_mode else "stub"
    print(f"Tool-call accuracy baseline ({mode}, {n_cases} cases x 2 paths)")
    print(sep)

    header = f"{'path':<10}{'decision':>10}{'name_acc':>10}{'arg_acc':>10}{'exact':>10}"
    header += f"{'FPR':>8}{'FNR':>8}{'parse':>8}{'avg_cnt':>9}"
    print(header)
    print("-" * len(header))
    for name, metrics in (("native", native_metrics), ("fallback", fallback_metrics)):
        print(
            f"{name:<10}"
            f"{metrics['decision_accuracy']:>10.4f}"
            f"{metrics['tool_name_accuracy']:>10.4f}"
            f"{metrics['argument_accuracy']:>10.4f}"
            f"{metrics['exact_match']:>10.4f}"
            f"{metrics['false_positive_rate']:>8.4f}"
            f"{metrics['false_negative_rate']:>8.4f}"
            f"{metrics['parse_success_rate']:>8.4f}"
            f"{metrics['avg_tool_count']:>9.4f}"
        )

    print(f"\nexecuted tool calls: native={native_exec}  fallback={fallback_exec}")

    print("\nPer-category exact_match (native / fallback):")
    cats = sorted(set(native_by_cat) | set(fallback_by_cat))
    for cat in cats:
        n_exact = native_by_cat.get(cat, {}).get("exact_match", 0.0)
        f_exact = fallback_by_cat.get(cat, {}).get("exact_match", 0.0)
        print(f"  {cat:<24}{n_exact:>8.4f}{f_exact:>10.4f}")

    if failures:
        print("\nFailure samples (exact_match == 0):")
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
    native: dict[str, float], fallback: dict[str, float]
) -> None:
    payload = {"native": native, "fallback": fallback}
    BASELINE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


# --------------------------------------------------------------------------- #
# The report fixture runs everything once; tests assert on it
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def eval_report(
    eval_cases: list[dict[str, Any]],
    native_llm: Any,
    fallback_llm: Any,
    real_mode: bool,
    model_name: str,
    recording_tools: dict[str, RecordingTool],
) -> dict[str, Any]:
    native_outcomes: list = []
    fallback_outcomes: list = []
    failures: list[str] = []

    # Native path
    for tool in recording_tools.values():
        tool.reset()
    for case in eval_cases:
        calls, parse_ok = _run_native(case, native_llm, real_mode, recording_tools)
        native_outcomes.append(outcome_from_case(case, calls, parse_ok))
    native_exec = sum(t.call_count for t in recording_tools.values())

    # Fallback path
    for tool in recording_tools.values():
        tool.reset()
    for case in eval_cases:
        calls, parse_ok = _run_fallback(case, fallback_llm, recording_tools)
        fallback_outcomes.append(outcome_from_case(case, calls, parse_ok))
    fallback_exec = sum(t.call_count for t in recording_tools.values())

    native_metrics = compute_metrics(native_outcomes)
    fallback_metrics = compute_metrics(fallback_outcomes)
    native_by_cat = compute_metrics_by_category(native_outcomes)
    fallback_by_cat = compute_metrics_by_category(fallback_outcomes)

    # Collect failures (native path; fallback is oracle-perfect in stub mode)
    for outcome in native_outcomes:
        m = score_case(outcome)
        if not m.exact:
            failures.append(
                f"  [native] {outcome.case_id} ({outcome.category}) "
                f"predicted={outcome.predicted_names} "
                f"expected={[c.name for c in outcome.expected_calls]}"
            )

    _print_report(
        native_metrics,
        fallback_metrics,
        native_by_cat,
        fallback_by_cat,
        failures,
        native_exec,
        fallback_exec,
        real_mode,
        model_name,
        len(eval_cases),
    )

    if os.getenv("EVAL_UPDATE_BASELINE") == "1":
        _write_baseline(native_metrics, fallback_metrics)
        print(
            f"[baseline] wrote {BASELINE_PATH.name} "
            f"(native + fallback) for {len(eval_cases)} cases"
        )

    return {
        "native": native_metrics,
        "fallback": fallback_metrics,
        "native_by_category": native_by_cat,
        "fallback_by_category": fallback_by_cat,
        "failures": failures,
        "real_mode": real_mode,
        "model_name": model_name,
        "n_cases": len(eval_cases),
        "native_exec": native_exec,
        "fallback_exec": fallback_exec,
    }


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
_EXPECTED_CATEGORIES = {
    "single_tool_keyword": 8,
    "single_tool_semantic": 6,
    "multi_tool": 6,
    "no_tool_casual": 6,
    "no_tool_emotional": 6,
    "args_edge": 4,
    "ambiguous": 4,
}


def test_dataset_integrity(eval_cases: list[dict[str, Any]]) -> None:
    """The dataset must be exactly 40 cases across the 7 fixed categories."""
    assert len(eval_cases) == 40, f"expected 40 cases, got {len(eval_cases)}"
    cats = Counter(c["category"] for c in eval_cases)
    assert dict(cats) == _EXPECTED_CATEGORIES, (
        f"category counts mismatch: {dict(cats)}"
    )
    seen: set[str] = set()
    for c in eval_cases:
        assert c["case_id"] not in seen, f"duplicate case_id: {c['case_id']}"
        seen.add(c["case_id"])
        assert c["user_message"]
        assert isinstance(c["enabled_tools"], list)
        exp = c["expected"]
        assert "should_call_tool" in exp
        assert "expected_tool_calls" in exp
        if exp["should_call_tool"]:
            assert len(exp["expected_tool_calls"]) >= 1, (
                f"{c['case_id']}: should_call but no expected calls"
            )
            for tc in exp["expected_tool_calls"]:
                assert tc["name"] in {
                    "search_diary",
                    "get_weather_info",
                    "get_user_address",
                    "analyze_sentiment",
                    "query_entity_graph",
                }, f"{c['case_id']}: unknown tool {tc['name']}"
        else:
            assert exp["expected_tool_calls"] == [], (
                f"{c['case_id']}: no-tool case must have empty expected calls"
            )


def test_native_path_runs(eval_report: dict[str, Any]) -> None:
    """Native path must produce a full metric block."""
    m = eval_report["native"]
    for key in METRIC_KEYS:
        assert key in m, f"native missing metric {key}"
    assert 0.0 <= m["decision_accuracy"] <= 1.0


def test_fallback_path_runs(eval_report: dict[str, Any]) -> None:
    """Fallback path must produce a full metric block."""
    m = eval_report["fallback"]
    for key in METRIC_KEYS:
        assert key in m, f"fallback missing metric {key}"
    assert 0.0 <= m["parse_success_rate"] <= 1.0


def test_stub_fallback_wiring(eval_report: dict[str, Any], real_mode: bool) -> None:
    """In stub mode the fallback (oracle) path must be perfect.

    This proves the parsing pipeline (parse_text_tag_calls) and the metric
    wiring are correct: given the expected text-tag input, every metric lands
    at 1.0. Real mode is skipped (the real LLM is imperfect by design).
    """
    if real_mode:
        pytest.skip("stub-wiring check only applies to stub mode")
    m = eval_report["fallback"]
    assert m["parse_success_rate"] == pytest.approx(1.0)
    assert m["decision_accuracy"] == pytest.approx(1.0)
    assert m["exact_match"] == pytest.approx(1.0)
    assert m["false_positive_rate"] == pytest.approx(0.0)
    assert m["false_negative_rate"] == pytest.approx(0.0)


def test_no_regression_vs_baseline(eval_report: dict[str, Any], real_mode: bool) -> None:
    """Soft per-path check: fail only on a real drop below the recorded value."""
    if not real_mode:
        pytest.skip("regression vs baseline only checked in real mode (LLM_API_KEY set)")
    baseline = _load_baseline()
    if not baseline or baseline.get("_placeholder"):
        pytest.skip(
            "placeholder baseline; seed with EVAL_UPDATE_BASELINE=1 make eval-tool"
        )

    regressions: list[str] = []
    for path in ("native", "fallback"):
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

    assert not regressions, "Tool-call regression vs baseline:\n" + "\n".join(
        regressions
    )
