"""Evaluate whether the model should call an MCP tool and which one.

Two modes, mirroring the other eval suites:

* **stub-oracle** (CI, no ``LLM_API_KEY``) — validates the dataset, both protocol
  parsers and the reused tool-call metrics; it makes no claim about real-model
  MCP decision quality.
* **real** (``MCP_DECISION_REAL=1`` + ``LLM_API_KEY``) — the model actually
  decides which MCP tool to call. ``EVAL_UPDATE_BASELINE=1`` reseeds
  ``baseline.json`` from that run, and the regression check below compares real
  runs against it only (stub runs never grad against a real baseline).
"""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.shared.tool_protocol import (
    extract_native_tool_calls,
    parse_text_tag_calls,
)
from tests.eval.mcp_decision.conftest import tool_specs_for
from tests.eval.tool_call.metrics import (
    METRIC_KEYS,
    compute_metrics,
    outcome_from_case,
    score_case,
)

pytestmark = pytest.mark.eval

BASELINE_PATH = Path(__file__).parent / "baseline.json"
EXPECTED_CATEGORIES = {
    "call_required": 4,
    "no_call": 4,
    "tool_selection": 4,
}
#: Real-model MCP decisions vary between runs (0.6667 / 0.75 observed on the same
#: 12 cases), so the gate only blocks a clear regression rather than noise.
REGRESSION_TOLERANCE = 0.15


def _write_baseline(
    model_metrics: dict[str, float],
    parser_metrics: dict[str, float],
    model_name: str,
    sample_count: int,
) -> None:
    payload = {
        "_placeholder": False,
        "_mode": "real",
        "_model": model_name,
        "_sample_count": sample_count,
        "_date": date.today().isoformat(),
        "_note": (
            "Seeded by EVAL_UPDATE_BASELINE=1 together with MCP_DECISION_REAL=1. "
            "CI keeps running the stub-oracle path; the regression check applies "
            "to real runs only."
        ),
        "mode": "real",
        "disclaimer": (
            "Real-model scores on a fixed 12-case set; the LLM decision varies "
            "run to run, so this is a regression floor, not a product-quality claim."
        ),
        "model": {key: model_metrics[key] for key in METRIC_KEYS},
        "parser": {key: parser_metrics[key] for key in METRIC_KEYS},
    }
    BASELINE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"[baseline] wrote {BASELINE_PATH.name} mode=real "
        f"model={model_name} samples={sample_count}"
    )


def _model_prompt(case: dict[str, Any], real_mode: bool) -> str:
    if real_mode:
        return case["user_message"]
    return f"[{case['case_id']}] {case['user_message']}"


@pytest.fixture(scope="module")
def eval_report(
    mcp_cases: list[dict[str, Any]],
    decision_llm: Any,
    oracle_llm: Any,
    real_mode: bool,
    model_name: str,
) -> dict[str, Any]:
    model_outcomes = []
    parser_outcomes = []

    for case in mcp_cases:
        bound = decision_llm.bind_tools(tool_specs_for(case))
        response = bound.invoke(_model_prompt(case, real_mode))
        model_calls = extract_native_tool_calls(response)
        model_outcomes.append(outcome_from_case(case, model_calls))

        oracle_response = oracle_llm.invoke(
            f"[{case['case_id']}] parser check"
        )
        parser_calls = parse_text_tag_calls(oracle_response.content)
        parser_outcomes.append(outcome_from_case(case, parser_calls))

    model_metrics = compute_metrics(model_outcomes)
    parser_metrics = compute_metrics(parser_outcomes)
    print(
        "\nMCP decision eval "
        f"mode={model_name} cases={len(mcp_cases)} "
        f"model_exact={model_metrics['exact_match']:.4f} "
        f"parser_exact={parser_metrics['exact_match']:.4f}"
    )
    if not real_mode:
        print(
            "stub-oracle placeholder: scores validate harness/parsing only; "
            "they are not real MCP decision quality."
        )
    elif os.getenv("EVAL_UPDATE_BASELINE") == "1":
        _write_baseline(model_metrics, parser_metrics, model_name, len(mcp_cases))
    return {
        "model": model_metrics,
        "parser": parser_metrics,
        "real_mode": real_mode,
    }


def test_dataset_integrity(mcp_cases: list[dict[str, Any]]) -> None:
    assert len(mcp_cases) == 12
    assert Counter(case["category"] for case in mcp_cases) == EXPECTED_CATEGORIES
    seen: set[str] = set()
    for case in mcp_cases:
        assert case["case_id"] not in seen
        seen.add(case["case_id"])
        assert case["user_message"]
        assert case["enabled_tools"]
        expected = case["expected"]
        calls = expected["expected_tool_calls"]
        assert bool(calls) is bool(expected["should_call_tool"])
        for call in calls:
            assert call["name"].startswith("mcp__")
            assert call["name"] in case["enabled_tools"]


def test_oracle_protocol_and_metric_wiring(
    eval_report: dict[str, Any], real_mode: bool
) -> None:
    """Oracle-perfect scores prove wiring only, never model quality."""
    parser = eval_report["parser"]
    for key in METRIC_KEYS:
        assert key in parser
    assert parser["parse_success_rate"] == pytest.approx(1.0)
    assert parser["exact_match"] == pytest.approx(1.0)
    if not real_mode:
        assert eval_report["model"]["exact_match"] == pytest.approx(1.0)


def test_metrics_detect_wrong_mcp_tool(mcp_cases: list[dict[str, Any]]) -> None:
    """A called-but-wrong MCP tool must fail name/exact scoring."""
    case = next(c for c in mcp_cases if c["category"] == "tool_selection")
    expected_name = case["expected"]["expected_tool_calls"][0]["name"]
    wrong_name = next(name for name in case["enabled_tools"] if name != expected_name)
    outcome = outcome_from_case(
        case,
        [{"name": wrong_name, "args": {"query": "wrong"}}],
    )
    metric = score_case(outcome)
    assert metric.decision_correct is True
    assert metric.name_score == 0.0
    assert metric.exact is False


def test_baseline_declares_mode_and_metadata() -> None:
    """The committed baseline must state which mode it was recorded in."""
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    mode = baseline.get("_mode", "stub-oracle")
    assert mode in {"real", "stub-oracle"}
    if mode == "stub-oracle":
        assert baseline["_placeholder"] is True
        assert baseline["mode"] == "stub-oracle"
        assert "not real quality" in baseline["disclaimer"].lower()
    else:
        assert baseline["_placeholder"] is False
        assert baseline["mode"] == "real"
        assert baseline["_model"] and baseline["_sample_count"] == 12
        assert baseline["_date"]
        assert "model" in baseline and "parser" in baseline


def test_no_regression_vs_baseline(
    eval_report: dict[str, Any], real_mode: bool
) -> None:
    """Real runs are compared against the recorded real floor, never the stub one."""
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    if baseline.get("_mode") != "real":
        pytest.skip("baseline is still the stub-oracle placeholder")
    if not real_mode:
        pytest.skip("stub-oracle run; real baseline is not comparable")

    recorded = baseline["model"]["exact_match"]
    current = eval_report["model"]["exact_match"]
    assert current >= recorded - REGRESSION_TOLERANCE, (
        f"MCP decision regressed: {current:.4f} < {recorded:.4f} "
        f"- {REGRESSION_TOLERANCE} (reseed with "
        "EVAL_UPDATE_BASELINE=1 MCP_DECISION_REAL=1 if the drop is expected)"
    )
