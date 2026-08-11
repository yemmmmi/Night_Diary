"""Performance statistics: p50/p95 latency, token aggregation, bottleneck spans.

Complements the simplistic ``/dev/stats`` endpoint (which only reports an
unweighted average duration) with percentile-based latency, per-agent token
cost breakdowns, error rates, and bottleneck span identification across the
trace_json span tree.

SQLite has no ``PERCENTILE_CONT`` window function, so percentiles are
computed in application code via sorted indexing.
"""

from __future__ import annotations

import contextlib
import json
import logging
from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from app.infrastructure.models.llm_call_log import LlmCallLogRow
from app.infrastructure.models.pipeline_trace import PipelineTraceRow

logger = logging.getLogger(__name__)


def percentile(values: list[float], q: float) -> float:
    """Calculate percentile via sorted indexing (SQLite has no PERCENTILE_CONT).

    Args:
        values: list of numeric values (need not be pre-sorted).
        q: quantile in ``[0.0, 1.0]`` — e.g. ``0.5`` for p50, ``0.95`` for p95.

    Returns:
        The value at the ``q`` quantile, or ``0.0`` for an empty list.
    """
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    idx = min(int(n * q), n - 1)
    return float(sorted_vals[idx])


def flatten_spans(trace_json: dict[str, Any]) -> list[tuple[str, float]]:
    """Recursively flatten a span tree from ``trace_json``.

    Walks the nested ``child_spans`` arrays at every depth and returns a flat
    list of ``(stage_name, duration_ms)`` tuples for all spans.

    Args:
        trace_json: a parsed trace payload whose ``spans`` key holds the
            root-level span list.

    Returns:
        Flat list of ``(stage_name, duration_ms)`` tuples. Spans without a
        ``duration_ms`` default to ``0``.
    """
    result: list[tuple[str, float]] = []
    spans = trace_json.get("spans", [])
    if not isinstance(spans, list):
        return result
    for span in spans:
        if not isinstance(span, dict):
            continue
        stage = span.get("stage_name", "?")
        dur = span.get("duration_ms", 0) or 0
        result.append((stage, float(dur)))
        children = span.get("child_spans", [])
        if isinstance(children, list) and children:
            result.extend(flatten_spans({"spans": children}))
    return result


def identify_bottlenecks(
    trace_jsons: list[dict[str, Any]], top_n: int = 3
) -> list[dict[str, Any]]:
    """Identify the top-N bottleneck spans across multiple traces.

    Aggregates durations by ``stage_name`` and ranks stages by average
    duration (descending).

    Args:
        trace_jsons: list of parsed trace payloads.
        top_n: maximum number of bottleneck stages to return.

    Returns:
        List of dicts, each with keys ``stage_name``, ``avg_ms``, ``p95_ms``,
        ``count``, and ``share`` (fraction of total span time).
    """
    stage_durations: dict[str, list[float]] = defaultdict(list)
    for trace_json in trace_jsons:
        for stage, dur in flatten_spans(trace_json):
            stage_durations[stage].append(dur)

    total_all = sum(sum(d) for d in stage_durations.values()) or 1.0
    bottlenecks: list[dict[str, Any]] = []
    for stage, durs in stage_durations.items():
        avg = sum(durs) / len(durs) if durs else 0.0
        p95 = percentile(durs, 0.95)
        share = sum(durs) / total_all
        bottlenecks.append(
            {
                "stage_name": stage,
                "avg_ms": round(avg, 1),
                "p95_ms": round(p95, 1),
                "count": len(durs),
                "share": round(share, 3),
            }
        )
    bottlenecks.sort(key=lambda x: x["avg_ms"], reverse=True)
    return bottlenecks[:top_n]


def get_performance_stats(
    db: Session, *, scenario: str | None = None, limit: int = 100
) -> dict[str, Any]:
    """Aggregate performance statistics across recent pipeline traces.

    Computes:
    * **Latency**: p50 / p95 of trace-level ``duration_ms``.
    * **Tokens**: total and per-agent breakdown of ``tokens_in`` /
      ``tokens_out`` with p50 / p95 latency per agent.
    * **Errors**: total error count and error rate across all LLM calls.
    * **Bottleneck spans**: top-3 stages by average duration, extracted from
      the ``trace_json`` span trees.

    Args:
        db: database session.
        scenario: optional scenario filter (e.g. ``"diary_analysis"``).
        limit: maximum number of recent traces to analyse (default 100).

    Returns:
        A dict with ``latency``, ``tokens``, ``errors``, and
        ``bottleneck_spans`` keys. Returns empty sub-dicts when no traces
        match.
    """
    # 1. Query recent pipeline traces.
    query = db.query(PipelineTraceRow)
    if scenario:
        query = query.filter(PipelineTraceRow.scenario == scenario)
    traces = (
        query.order_by(PipelineTraceRow.created_at.desc()).limit(limit).all()
    )

    if not traces:
        return {"latency": {}, "tokens": {}, "errors": {}, "bottleneck_spans": []}

    trace_ids = [t.trace_id for t in traces]
    durations = [t.duration_ms for t in traces if t.duration_ms is not None]

    # 2. Latency p50 / p95.
    latency = {
        "trace_p50_ms": round(percentile(durations, 0.5), 1),
        "trace_p95_ms": round(percentile(durations, 0.95), 1),
        "trace_count": len(traces),
    }

    # 3. LLM call stats grouped by agent_name.
    llm_logs: list[LlmCallLogRow] = (
        db.query(LlmCallLogRow).filter(LlmCallLogRow.trace_id.in_(trace_ids)).all()
    )

    by_agent: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "latencies": [],
            "tokens_in": [],
            "tokens_out": [],
            "errors": 0,
            "count": 0,
        }
    )
    for log in llm_logs:
        agent = log.agent_name or "unknown"
        by_agent[agent]["latencies"].append(log.latency_ms or 0)
        by_agent[agent]["tokens_in"].append(log.tokens_in or 0)
        by_agent[agent]["tokens_out"].append(log.tokens_out or 0)
        if log.error:
            by_agent[agent]["errors"] += 1
        by_agent[agent]["count"] += 1

    agent_stats: dict[str, dict[str, Any]] = {}
    total_in = 0
    total_out = 0
    total_errors = 0
    for agent, data in by_agent.items():
        cnt = data["count"] or 1
        avg_in = sum(data["tokens_in"]) / cnt
        avg_out = sum(data["tokens_out"]) / cnt
        agent_stats[agent] = {
            "p50_ms": round(percentile(data["latencies"], 0.5), 1),
            "p95_ms": round(percentile(data["latencies"], 0.95), 1),
            "avg_tokens_in": round(avg_in, 1),
            "avg_tokens_out": round(avg_out, 1),
            "count": cnt,
            "error_count": data["errors"],
        }
        total_in += sum(data["tokens_in"])
        total_out += sum(data["tokens_out"])
        total_errors += data["errors"]

    # 4. Bottleneck spans — parse trace_json span trees.
    trace_jsons: list[dict[str, Any]] = []
    for t in traces:
        if t.trace_json:
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                trace_jsons.append(json.loads(t.trace_json))

    bottlenecks = identify_bottlenecks(trace_jsons, top_n=3)

    return {
        "latency": latency,
        "tokens": {
            "total_in": total_in,
            "total_out": total_out,
            "by_agent": agent_stats,
        },
        "errors": {
            "total": total_errors,
            "total_llm_calls": len(llm_logs),
            "rate": round(total_errors / len(llm_logs), 3) if llm_logs else 0.0,
        },
        "bottleneck_spans": bottlenecks,
    }
