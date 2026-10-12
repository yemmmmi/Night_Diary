"""Result-delivery abstraction for scheduled tasks (E4).

Hermes' cron can deliver a task's output back to the originating session, a
local file, or a configured platform target. 夜记 keeps the same seam: every
scheduled-task result is handed to a :class:`ResultSink` chosen per task (the
``sink`` field, default ``inbox``).

The default :class:`InboxResultSink` targets the in-app mailbox — which, in
夜记, *is* the execution receipt already persisted by the store, so it is a
deliberate no-op that documents the channel and keeps the delivery contract
uniform. A future channel (local file, IM push) registers another
implementation via :func:`register_sink` without touching the execution path.

Delivery is best-effort: a failing sink is logged and never fails the run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)

#: Default result-delivery channel name.
DEFAULT_SINK = "inbox"


@dataclass(frozen=True)
class TaskResult:
    """One scheduled-task outcome handed to a sink for delivery."""

    user_id: str
    task_id: str
    kind: str
    mode: str
    status: str  # done | failed
    title: str
    body: str
    run_id: int | None = None


@runtime_checkable
class ResultSink(Protocol):
    """A delivery channel for a scheduled-task result."""

    name: str

    def deliver(self, result: TaskResult) -> None:
        """Deliver ``result``; implementations must be best-effort."""
        ...


class InboxResultSink:
    """Default sink — the scheduled-task run receipt IS the in-app mailbox entry.

    ``execute_scheduled_task`` persists the receipt (``summary`` / ``error``)
    before invoking the sink, so this sink has nothing extra to write. It exists
    so the delivery contract is uniform across channels.
    """

    name = DEFAULT_SINK

    def deliver(self, result: TaskResult) -> None:
        return None


class LogResultSink:
    """Optional sink that mirrors results to the process log (ops / debugging)."""

    name = "log"

    def deliver(self, result: TaskResult) -> None:
        logger.info(
            "scheduled result task=%s kind=%s mode=%s status=%s: %s",
            result.task_id,
            result.kind,
            result.mode,
            result.status,
            result.body,
        )


_SINKS: dict[str, ResultSink] = {}


def register_sink(sink: ResultSink) -> None:
    """Register (or replace) a sink under its ``name``."""
    _SINKS[sink.name] = sink


def get_sink(name: str | None = None) -> ResultSink:
    """Return the sink named ``name`` (falling back to the default)."""
    return _SINKS.get(name or DEFAULT_SINK) or _SINKS[DEFAULT_SINK]


def available_sinks() -> list[str]:
    """Registered sink names, in registration order."""
    return list(_SINKS)


register_sink(InboxResultSink())
register_sink(LogResultSink())


__all__ = [
    "DEFAULT_SINK",
    "InboxResultSink",
    "LogResultSink",
    "ResultSink",
    "TaskResult",
    "available_sinks",
    "get_sink",
    "register_sink",
]