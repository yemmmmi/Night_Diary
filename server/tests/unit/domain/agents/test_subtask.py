"""Unit tests for the D4 SubTaskRunner (bounded sub-task isolation).

The runner is the reusable primitive behind the weekly multi-dimensional
analysis: isolated per-task context, a concurrency cap, summary-only backflow,
and graceful degradation. These tests pin those four properties.
"""

from __future__ import annotations

import asyncio

from app.domain.agents.subtask import (
    SubTask,
    SubTaskOutcome,
    SubTaskRunner,
    format_subtask_summaries,
    summarize,
)


def test_summarize_collapses_whitespace() -> None:
    assert summarize("  今天\n\n过得  还不错 ") == "今天 过得 还不错"


def test_summarize_caps_length_with_ellipsis() -> None:
    out = summarize("字" * 100, 10)
    assert len(out) == 10
    assert out.endswith("…")


def test_summarize_keeps_short_text_untouched() -> None:
    assert summarize("短摘要", 50) == "短摘要"


def test_summarize_handles_none_like_input() -> None:
    assert summarize("") == ""


async def test_empty_input_returns_empty_list() -> None:
    async def worker(task: SubTask) -> str:
        return "unused"

    assert await SubTaskRunner(worker).run([]) == []


async def test_outcomes_preserve_input_order() -> None:
    async def worker(task: SubTask) -> str:
        # Later tasks finish first; order must still follow the input.
        await asyncio.sleep(0.03 if task.name == "a" else 0.0)
        return task.name

    runner = SubTaskRunner(worker)
    tasks = [SubTask(name=n, context="") for n in ("a", "b", "c")]
    outcomes = await runner.run(tasks)

    assert [o.name for o in outcomes] == ["a", "b", "c"]
    assert all(o.ok for o in outcomes)


async def test_long_output_is_reduced_to_summary() -> None:
    async def worker(task: SubTask) -> str:
        return "啰" * 500

    runner = SubTaskRunner(worker, max_summary_chars=20)
    (outcome,) = await runner.run([SubTask(name="情绪曲线", context="")])

    assert outcome.ok
    assert len(outcome.summary) == 20
    assert outcome.summary.endswith("…")


async def test_concurrency_is_capped() -> None:
    active = 0
    peak = 0

    async def worker(task: SubTask) -> str:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.02)
        active -= 1
        return task.name

    runner = SubTaskRunner(worker, max_concurrency=2)
    tasks = [SubTask(name=f"t{i}", context="") for i in range(5)]
    outcomes = await runner.run(tasks)

    assert peak <= 2
    assert len(outcomes) == 5
    assert all(o.ok for o in outcomes)


async def test_failure_degrades_without_aborting_batch() -> None:
    async def worker(task: SubTask) -> str:
        if task.name == "bad":
            raise RuntimeError("boom")
        return "ok"

    runner = SubTaskRunner(worker)
    outcomes = await runner.run([SubTask(name="good", context=""), SubTask(name="bad", context="")])
    by_name = {o.name: o for o in outcomes}

    assert by_name["good"].ok and by_name["good"].summary == "ok"
    assert not by_name["bad"].ok
    assert by_name["bad"].summary == ""
    assert "boom" in by_name["bad"].error


async def test_timeout_degrades() -> None:
    async def worker(task: SubTask) -> str:
        await asyncio.sleep(1.0)
        return "late"

    runner = SubTaskRunner(worker, timeout_s=0.02)
    (outcome,) = await runner.run([SubTask(name="slow", context="")])

    assert not outcome.ok
    assert "timeout" in outcome.error
    assert outcome.summary == ""


def test_format_subtask_summaries_skips_empty() -> None:
    outcomes = [
        SubTaskOutcome(name="情绪曲线", summary="平稳", ok=True),
        SubTaskOutcome(name="计划执行", summary="", ok=False, error="boom"),
    ]
    assert format_subtask_summaries(outcomes) == "- 情绪曲线：平稳"


def test_format_subtask_summaries_empty_when_no_summaries() -> None:
    assert format_subtask_summaries([SubTaskOutcome(name="x", summary="", ok=False)]) == ""