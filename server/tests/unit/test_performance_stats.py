"""Tests for performance stats service (V3 P5).

Covers the pure helper functions (percentile, flatten_spans,
identify_bottlenecks) and the DB-backed ``get_performance_stats`` which
aggregates p50/p95 latency, token costs, error rates, and bottleneck spans.
"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.infrastructure.models.llm_call_log import LlmCallLogRow
from app.infrastructure.models.pipeline_trace import PipelineTraceRow
from app.services.performance_stats_service import (
    flatten_spans,
    get_performance_stats,
    identify_bottlenecks,
    percentile,
)

# ── percentile ──────────────────────────────────────────────────────────


def test_percentile_empty_list() -> None:
    """An empty list yields 0.0 for any quantile."""
    assert percentile([], 0.5) == 0.0
    assert percentile([], 0.95) == 0.0


def test_percentile_single_value() -> None:
    """A single value is the result for every quantile."""
    assert percentile([100.0], 0.5) == 100.0
    assert percentile([100.0], 0.95) == 100.0


def test_percentile_basic() -> None:
    """Ten evenly spaced values: p50 picks index 5 (60), p95 index 9 (100)."""
    values = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    assert percentile(values, 0.5) == 60
    assert percentile(values, 0.95) == 100


def test_percentile_p0_and_p100() -> None:
    """q=0.0 returns the min, q=1.0 returns the max."""
    values = [5, 3, 8, 1, 9]
    assert percentile(values, 0.0) == 1
    assert percentile(values, 1.0) == 9


def test_percentile_unsorted_input() -> None:
    """percentile sorts internally so unsorted input still works."""
    values = [100, 10, 50, 30, 70]
    assert percentile(values, 0.5) == 50


# ── flatten_spans ───────────────────────────────────────────────────────


def test_flatten_spans_simple() -> None:
    """Flatten a two-level span tree into a flat (stage, dur) list."""
    trace_json = {
        "spans": [
            {"stage_name": "S1", "duration_ms": 100, "child_spans": []},
            {
                "stage_name": "S2",
                "duration_ms": 200,
                "child_spans": [
                    {"stage_name": "S2.1", "duration_ms": 50, "child_spans": []},
                ],
            },
        ],
    }
    flat = flatten_spans(trace_json)
    assert len(flat) == 3
    stages = [s[0] for s in flat]
    assert "S1" in stages
    assert "S2" in stages
    assert "S2.1" in stages


def test_flatten_spans_empty() -> None:
    """Empty dicts and empty span lists yield []."""
    assert flatten_spans({}) == []
    assert flatten_spans({"spans": []}) == []


def test_flatten_spans_deep_nesting() -> None:
    """Three-level nesting is fully traversed."""
    trace_json = {
        "spans": [
            {
                "stage_name": "A",
                "duration_ms": 10,
                "child_spans": [
                    {
                        "stage_name": "B",
                        "duration_ms": 20,
                        "child_spans": [
                            {"stage_name": "C", "duration_ms": 30, "child_spans": []},
                        ],
                    },
                ],
            },
        ],
    }
    flat = flatten_spans(trace_json)
    assert len(flat) == 3
    durations = dict(flat)
    assert durations["A"] == 10
    assert durations["B"] == 20
    assert durations["C"] == 30


def test_flatten_spans_missing_duration_defaults_zero() -> None:
    """A span without duration_ms defaults to 0."""
    trace_json = {"spans": [{"stage_name": "X", "child_spans": []}]}
    flat = flatten_spans(trace_json)
    assert flat == [("X", 0)]


# ── identify_bottlenecks ────────────────────────────────────────────────


def test_bottleneck_spans() -> None:
    """S2 has the highest average duration, so it ranks first."""
    traces = [
        {
            "spans": [
                {"stage_name": "S1", "duration_ms": 100, "child_spans": []},
                {"stage_name": "S2", "duration_ms": 500, "child_spans": []},
                {"stage_name": "S3", "duration_ms": 200, "child_spans": []},
            ],
        },
        {
            "spans": [
                {"stage_name": "S1", "duration_ms": 120, "child_spans": []},
                {"stage_name": "S2", "duration_ms": 480, "child_spans": []},
                {"stage_name": "S3", "duration_ms": 210, "child_spans": []},
            ],
        },
    ]
    bottlenecks = identify_bottlenecks(traces, top_n=3)
    assert len(bottlenecks) <= 3
    # S2 should be the biggest bottleneck.
    assert bottlenecks[0]["stage_name"] == "S2"
    assert bottlenecks[0]["avg_ms"] > 400


def test_bottleneck_spans_respects_top_n() -> None:
    """top_n limits the number of returned bottlenecks."""
    traces = [
        {
            "spans": [
                {"stage_name": f"S{i}", "duration_ms": i * 100, "child_spans": []}
                for i in range(1, 6)
            ],
        },
    ]
    bottlenecks = identify_bottlenecks(traces, top_n=2)
    assert len(bottlenecks) == 2
    # Descending by avg_ms: S5 first, S4 second.
    assert bottlenecks[0]["stage_name"] == "S5"
    assert bottlenecks[1]["stage_name"] == "S4"


def test_bottleneck_spans_empty() -> None:
    """No traces yields no bottlenecks."""
    assert identify_bottlenecks([], top_n=3) == []


def test_bottleneck_share_field() -> None:
    """Each bottleneck has a 'share' between 0 and 1."""
    traces = [
        {
            "spans": [
                {"stage_name": "A", "duration_ms": 300, "child_spans": []},
                {"stage_name": "B", "duration_ms": 100, "child_spans": []},
            ],
        },
    ]
    bottlenecks = identify_bottlenecks(traces, top_n=3)
    total_share = sum(b["share"] for b in bottlenecks)
    assert abs(total_share - 1.0) < 0.01  # shares sum to ~1.0
    # A is 75% of the total duration.
    assert bottlenecks[0]["stage_name"] == "A"
    assert bottlenecks[0]["share"] == 0.75


# ── get_performance_stats (DB-backed) ───────────────────────────────────


def _make_trace_row(
    trace_id: str,
    *,
    scenario: str = "diary_analysis",
    duration_ms: float = 1000.0,
    span_json: str | None = None,
) -> PipelineTraceRow:
    return PipelineTraceRow(
        trace_id=trace_id,
        scenario=scenario,
        user_id="u1",
        status="completed",
        started_at="2026-01-01T00:00:00",
        ended_at="2026-01-01T00:00:01",
        duration_ms=duration_ms,
        span_count=2,
        trace_json=span_json or "",
    )


def _make_llm_row(
    row_id: str,
    *,
    trace_id: str,
    agent_name: str = "empathy",
    latency_ms: float = 500.0,
    tokens_in: int = 100,
    tokens_out: int = 50,
    error: str | None = None,
) -> LlmCallLogRow:
    return LlmCallLogRow(
        id=row_id,
        user_id="u1",
        decision_id="dec-1",
        agent_name=agent_name,
        call_type="generate",
        model="deepseek-chat",
        latency_ms=latency_ms,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        error=error,
        created_at=0.0,
        trace_id=trace_id,
    )


def test_get_performance_stats_empty(db_session: Session) -> None:
    """No traces → empty stats structure."""
    result = get_performance_stats(db_session)
    assert result["latency"] == {}
    assert result["tokens"] == {}
    assert result["bottleneck_spans"] == []


def test_get_performance_stats_with_data(db_session: Session) -> None:
    """Full integration: traces + LLM logs yield latency, tokens, bottlenecks."""
    trace_json = json.dumps({
        "trace_id": "t1",
        "spans": [
            {"stage_name": "retrieve", "duration_ms": 100, "child_spans": []},
            {"stage_name": "generate", "duration_ms": 800, "child_spans": []},
        ],
    })
    db_session.add(_make_trace_row("t1", duration_ms=1000.0, span_json=trace_json))
    db_session.add(_make_trace_row("t2", duration_ms=2000.0, span_json=trace_json))
    db_session.add(
        _make_llm_row("l1", trace_id="t1", agent_name="empathy", latency_ms=800)
    )
    db_session.add(
        _make_llm_row("l2", trace_id="t2", agent_name="empathy", latency_ms=900)
    )
    db_session.commit()

    result = get_performance_stats(db_session)

    # Latency.
    assert result["latency"]["trace_count"] == 2
    assert result["latency"]["trace_p50_ms"] > 0
    assert result["latency"]["trace_p95_ms"] >= result["latency"]["trace_p50_ms"]

    # Tokens.
    assert result["tokens"]["total_in"] == 200  # 2 x 100
    assert result["tokens"]["total_out"] == 100  # 2 x 50
    assert "empathy" in result["tokens"]["by_agent"]
    agent_stat = result["tokens"]["by_agent"]["empathy"]
    assert agent_stat["count"] == 2
    assert agent_stat["avg_tokens_in"] == 100.0

    # Bottleneck: "generate" (800) > "retrieve" (100).
    bn = result["bottleneck_spans"]
    assert len(bn) > 0
    assert bn[0]["stage_name"] == "generate"
    assert bn[0]["avg_ms"] == 800.0


def test_get_performance_stats_error_rate(db_session: Session) -> None:
    """Error rate is computed from LlmCallLogRow.error."""
    db_session.add(_make_trace_row("t1"))
    db_session.add(_make_llm_row("l1", trace_id="t1", error="timeout"))
    db_session.add(_make_llm_row("l2", trace_id="t1"))
    db_session.commit()

    result = get_performance_stats(db_session)
    assert result["errors"]["total"] == 1
    assert result["errors"]["total_llm_calls"] == 2
    assert result["errors"]["rate"] == 0.5


def test_get_performance_stats_scenario_filter(db_session: Session) -> None:
    """The scenario filter scopes the traces that are analysed."""
    db_session.add(
        _make_trace_row("t1", scenario="diary_analysis", duration_ms=100.0)
    )
    db_session.add(
        _make_trace_row("t2", scenario="conversation", duration_ms=999.0)
    )
    db_session.commit()

    result = get_performance_stats(db_session, scenario="conversation")
    assert result["latency"]["trace_count"] == 1
    assert result["latency"]["trace_p50_ms"] == 999.0
