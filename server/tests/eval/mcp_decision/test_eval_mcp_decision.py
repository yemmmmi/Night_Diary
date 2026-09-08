"""Evaluate whether the model should call an MCP tool and which one.

The default CI path is an explicit oracle/placeholder run. It validates the
dataset, both protocol parsers, and reused tool-call metrics; it makes no claim
about real-model MCP decision quality.
"""

from __future__ import annotations

import json
from collections import Counter
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


def test_placeholder_baseline_is_explicit() -> None:
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    assert baseline["_placeholder"] is True
    assert baseline["mode"] == "stub-oracle"
    assert "not real quality" in baseline["disclaimer"].lower()
