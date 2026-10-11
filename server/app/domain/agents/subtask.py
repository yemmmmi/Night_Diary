"""SubTaskRunner — bounded sub-task isolation (D4).

Hermes' ``delegate_task`` runs sub-agents in isolated contexts with a capped
concurrency (default 3) and expects only a summary back. D4 borrows that shape
*without* introducing a generic delegation tool: no tool access, no nested
agents, no free-form fan-out.

The primitive here is deliberately small:

* **isolated context** — each :class:`SubTask` carries only the slice of data it
  is allowed to see; the runner never hands a sub-task the parent's full state.
* **summary-only backflow** — a worker's raw output is squeezed through
  :func:`summarize` (whitespace-collapsed, length-capped) before it can flow
  back, so a verbose sub-task can never dump unbounded text into the parent.
* **concurrency cap** — at most ``max_concurrency`` sub-tasks run at once
  (reusing :data:`~app.domain.agents.graph.DEFAULT_MAX_CONCURRENCY`).
* **graceful degradation** — a failing/timing-out sub-task yields an empty,
  non-fatal outcome; one bad sub-task never aborts the batch.

The weekly report's multi-dimensional analysis is the first consumer.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from app.domain.agents.graph import DEFAULT_MAX_CONCURRENCY

logger = logging.getLogger(__name__)

DEFAULT_SUBTASK_TIMEOUT_S = 20.0
DEFAULT_MAX_SUMMARY_CHARS = 300
_ELLIPSIS = "…"


@dataclass(frozen=True)
class SubTask:
    """A single isolated unit of work handed to the runner."""

    name: str
    context: str
    instruction: str = ""


@dataclass(frozen=True)
class SubTaskOutcome:
    """The bounded result of one sub-task (summary only)."""

    name: str
    summary: str
    ok: bool
    error: str = ""


#: A worker receives one isolated sub-task and returns raw text; the runner
#: applies the summary-only constraint.
SubTaskWorker = Callable[[SubTask], Awaitable[str]]


def summarize(text: str, max_chars: int = DEFAULT_MAX_SUMMARY_CHARS) -> str:
    """Collapse whitespace and cap ``text`` at ``max_chars`` (summary-only)."""
    collapsed = " ".join((text or "").split())
    if max_chars <= 0 or len(collapsed) <= max_chars:
        return collapsed
    return collapsed[: max_chars - len(_ELLIPSIS)].rstrip() + _ELLIPSIS


class SubTaskRunner:
    """Run sub-tasks concurrently with a cap and summary-only backflow."""

    def __init__(
        self,
        worker: SubTaskWorker,
        *,
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
        max_summary_chars: int = DEFAULT_MAX_SUMMARY_CHARS,
        timeout_s: float = DEFAULT_SUBTASK_TIMEOUT_S,
    ) -> None:
        self._worker = worker
        self._max_concurrency = max(1, max_concurrency)
        self._max_summary_chars = max_summary_chars
        self._timeout = timeout_s

    async def run(self, subtasks: Sequence[SubTask]) -> list[SubTaskOutcome]:
        """Run every sub-task, returning outcomes in input order."""
        if not subtasks:
            return []
        semaphore = asyncio.Semaphore(self._max_concurrency)
        results = await asyncio.gather(
            *(self._run_one(task, semaphore) for task in subtasks),
            return_exceptions=True,
        )
        outcomes: list[SubTaskOutcome] = []
        for task, result in zip(subtasks, results, strict=True):
            if isinstance(result, BaseException):
                logger.error("subtask %s raised past safety wrapper: %r", task.name, result)
                outcomes.append(
                    SubTaskOutcome(name=task.name, summary="", ok=False, error=f"crashed: {result!r}")
                )
            else:
                outcomes.append(result)
        return outcomes

    async def _run_one(
        self, task: SubTask, semaphore: asyncio.Semaphore
    ) -> SubTaskOutcome:
        async def _bounded() -> str:
            async with semaphore:
                return await self._worker(task)

        try:
            raw = await asyncio.wait_for(_bounded(), timeout=self._timeout)
        except asyncio.TimeoutError:  # noqa: UP041
            logger.warning("subtask %s timed out after %.1fs", task.name, self._timeout)
            return SubTaskOutcome(
                name=task.name, summary="", ok=False, error=f"timeout after {self._timeout}s"
            )
        except Exception as exc:
            logger.warning("subtask %s failed (%s)", task.name, type(exc).__name__)
            return SubTaskOutcome(
                name=task.name, summary="", ok=False, error=f"{type(exc).__name__}: {exc}"
            )
        return SubTaskOutcome(
            name=task.name,
            summary=summarize(raw, self._max_summary_chars),
            ok=True,
        )


def format_subtask_summaries(outcomes: Sequence[SubTaskOutcome]) -> str:
    """Render non-empty summaries as a bullet block for prompt injection."""
    lines = [f"- {o.name}：{o.summary}" for o in outcomes if o.summary]
    return "\n".join(lines)


__all__ = [
    "DEFAULT_MAX_SUMMARY_CHARS",
    "DEFAULT_SUBTASK_TIMEOUT_S",
    "SubTask",
    "SubTaskOutcome",
    "SubTaskRunner",
    "SubTaskWorker",
    "format_subtask_summaries",
    "summarize",
]