"""Pipeline tracing for developer-mode observability.

Provides ``PipelineTrace`` / ``TraceSpan`` data structures and a ``trace_span``
context manager that capture stage-level input/output snapshots, timing, and
errors for inspection in the developer-mode UI.

When developer mode is off (no trace set in the context), ``trace_span`` yields
``None`` with zero overhead -- production code paths are unaffected.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# Span status constants
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_ERROR = "error"
STATUS_DISPATCHED = "dispatched"


def truncate_snapshot(
    value: Any,
    max_str: int = 500,
    max_dict_keys: int = 20,
    max_list_items: int = 3,
) -> Any:
    """Recursively truncate a snapshot value for safe inspection.

    - Strings longer than ``max_str`` are truncated with an ellipsis suffix.
    - Dicts with more than ``max_dict_keys`` keys keep only the first N and
      append a ``__truncated__`` marker indicating the overflow count.
    - Lists/tuples with more than ``max_list_items`` items keep only the first
      N and append a marker indicating the overflow count.
    - Nested dicts/lists are processed recursively.
    - All other types (int, float, bool, None, ...) are returned unchanged.
    """
    if isinstance(value, str):
        if len(value) > max_str:
            return value[:max_str] + f"...[truncated, {len(value)} chars total]"
        return value

    if isinstance(value, dict):
        result: dict[Any, Any] = {}
        for i, (k, v) in enumerate(value.items()):
            if i >= max_dict_keys:
                result["__truncated__"] = f"...{len(value) - max_dict_keys} more keys"
                break
            result[k] = truncate_snapshot(v, max_str, max_dict_keys, max_list_items)
        return result

    if isinstance(value, list):
        items: list[Any] = []
        for i, item in enumerate(value):
            if i >= max_list_items:
                items.append(f"...[{len(value) - max_list_items} more items]")
                break
            items.append(truncate_snapshot(item, max_str, max_dict_keys, max_list_items))
        return items

    return value


@dataclass
class TraceSpan:
    """One stage in a pipeline trace.

    Spans form a tree via ``child_spans``. Each span records its input/output
    snapshots (truncated for safety), timing, and an optional error.
    """

    span_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    stage_name: str = ""
    stage_label: str = ""
    status: str = STATUS_RUNNING
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    ended_at: datetime | None = None
    duration_ms: float = 0.0
    input_snapshot: Any = None
    output_snapshot: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)
    child_spans: list[TraceSpan] = field(default_factory=list)
    error: str | None = None

    def set_output(
        self,
        output: Any,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Set the output snapshot (truncated) and optionally merge metadata."""
        self.output_snapshot = truncate_snapshot(output)
        if metadata:
            self.metadata.update(metadata)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict suitable for JSON transport."""
        return {
            "span_id": self.span_id,
            "stage_name": self.stage_name,
            "stage_label": self.stage_label,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_ms": self.duration_ms,
            "input_snapshot": self.input_snapshot,
            "output_snapshot": self.output_snapshot,
            "metadata": self.metadata,
            "child_spans": [child.to_dict() for child in self.child_spans],
            "error": self.error,
        }


@dataclass
class PipelineTrace:
    """Top-level pipeline trace with nested span support.

    Spans are organised as a tree: ``start_span`` nests under the current
    top-of-stack span (if any), otherwise appends to the root ``spans`` list.
    The internal ``_span_stack`` tracks the currently-open span chain.
    """

    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    scenario: str = ""
    user_id: str = ""
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    status: str = STATUS_RUNNING
    ended_at: datetime | None = None
    duration_ms: float = 0.0
    spans: list[TraceSpan] = field(default_factory=list)
    _span_stack: list[TraceSpan] = field(default_factory=list)

    def start_span(
        self,
        stage_name: str,
        stage_label: str = "",
        *,
        input_snapshot: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> TraceSpan:
        """Start a new span.

        If there is an active span on the stack, the new span is appended to
        that span's ``child_spans``; otherwise it is appended to the trace's
        top-level ``spans`` list.
        """
        span = TraceSpan(
            stage_name=stage_name,
            stage_label=stage_label,
            input_snapshot=truncate_snapshot(input_snapshot)
            if input_snapshot is not None
            else None,
            metadata=dict(metadata) if metadata else {},
        )
        if self._span_stack:
            self._span_stack[-1].child_spans.append(span)
        else:
            self.spans.append(span)
        self._span_stack.append(span)
        return span

    def end_span(
        self,
        *,
        status: str = STATUS_COMPLETED,
        error: str | None = None,
        output: Any = None,
    ) -> TraceSpan | None:
        """End the current span, popping it from the stack.

        Sets ``ended_at``, ``duration_ms``, and ``status``. If ``output`` is
        provided, it is truncated and stored as ``output_snapshot``. If
        ``error`` is provided, it is recorded on the span.

        Returns the ended span, or ``None`` if the stack was empty.
        """
        if not self._span_stack:
            return None
        span = self._span_stack.pop()
        span.ended_at = datetime.now(UTC)
        span.duration_ms = (span.ended_at - span.started_at).total_seconds() * 1000
        span.status = status
        if error is not None:
            span.error = error
        if output is not None:
            span.output_snapshot = truncate_snapshot(output)
        return span

    def end(self, status: str = STATUS_COMPLETED) -> None:
        """Finalize the entire trace."""
        self.ended_at = datetime.now(UTC)
        self.duration_ms = (self.ended_at - self.started_at).total_seconds() * 1000
        self.status = status

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict suitable for JSON transport."""
        return {
            "trace_id": self.trace_id,
            "scenario": self.scenario,
            "user_id": self.user_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "status": self.status,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_ms": self.duration_ms,
            "spans": [span.to_dict() for span in self.spans],
        }


# ── Context propagation ──────────────────────────────────────────────────

_current_trace: ContextVar[PipelineTrace | None] = ContextVar(
    "night_diary_pipeline_trace",
    default=None,
)


def get_trace() -> PipelineTrace | None:
    """Return the current pipeline trace for this context, or ``None``."""
    return _current_trace.get()


def set_trace(trace: PipelineTrace | None) -> ContextVar[PipelineTrace | None]:
    """Set the current pipeline trace for this context."""
    return _current_trace.set(trace)


def reset_trace(token: ContextVar[PipelineTrace | None]) -> None:
    """Reset the context trace to its previous value using a token from ``set_trace``."""
    _current_trace.reset(token)


# ── Context manager ──────────────────────────────────────────────────────


@contextmanager
def trace_span(
    stage_name: str,
    stage_label: str = "",
    *,
    input_snapshot: Any = None,
    metadata: dict[str, Any] | None = None,
) -> Generator[TraceSpan | None, None, None]:
    """Context manager for tracing a pipeline stage.

    When developer mode is off (no trace set in the context), yields ``None``
    with zero overhead -- no span is created, no timing is recorded.

    When a trace is active, a ``TraceSpan`` is created and yielded. On normal
    exit the span is marked ``completed``. If an exception occurs inside the
    ``with`` block, the span is marked ``error`` with the exception message and
    the exception is re-raised.
    """
    trace = get_trace()
    if trace is None:
        yield None
        return

    span = trace.start_span(
        stage_name=stage_name,
        stage_label=stage_label,
        input_snapshot=input_snapshot,
        metadata=metadata,
    )
    try:
        yield span
    except Exception as exc:
        trace.end_span(status=STATUS_ERROR, error=str(exc))
        _try_publish_span(trace, span)
        raise
    else:
        trace.end_span(status=STATUS_COMPLETED)
        _try_publish_span(trace, span)


def _try_publish_span(trace: "PipelineTrace", span: "TraceSpan") -> None:
    """Best-effort push of a ``span_complete`` event to the SSE event bus.

    Called from ``trace_span.__exit__`` which runs in sync worker threads.
    Uses ``publish_span_complete_sync`` (thread-safe via
    ``call_soon_threadsafe``) so the event reaches SSE subscribers on the
    main event loop.  Failures are logged inside the helper and never
    propagate — tracing must not break the pipeline.
    """
    try:
        from app.shared.trace_persistence import publish_span_complete_sync

        publish_span_complete_sync(trace, span)
    except Exception:
        pass
