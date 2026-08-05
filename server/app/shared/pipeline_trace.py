"""用于开发者模式可观测性的管道追踪。

提供 ``PipelineTrace`` / ``TraceSpan`` 数据结构以及 ``trace_span`` 上下文
管理器，用于捕获阶段级的输入/输出快照、计时和错误，供开发者模式 UI 检查。

当开发者模式关闭时（上下文中未设置 trace），``trace_span`` 产出 ``None`` 且
零开销——生产代码路径不受影响。
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# Span 状态常量
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
    """递归地截断快照值，以便安全检查。

    - 长度超过 ``max_str`` 的字符串被截断并附加省略号后缀。
    - 键数量超过 ``max_dict_keys`` 的字典仅保留前 N 个，并附加一个
      ``__truncated__`` 标记以指示溢出数量。
    - 元素数量超过 ``max_list_items`` 的列表/元组仅保留前 N 个，并附加一个
      标记以指示溢出数量。
    - 嵌套的字典/列表会被递归处理。
    - 所有其他类型（int、float、bool、None……）原样返回。
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
    """管道追踪中的一个阶段。

    Span 通过 ``child_spans`` 形成树结构。每个 span 记录其输入/输出快照
    （为安全起见已截断）、计时以及可选的错误。
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
        """设置输出快照（已截断），并可选地合并元数据。"""
        self.output_snapshot = truncate_snapshot(output)
        if metadata:
            self.metadata.update(metadata)

    def to_dict(self) -> dict[str, Any]:
        """序列化为适合 JSON 传输的纯字典。"""
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
    """支持嵌套 span 的顶层管道追踪。

    Span 组织为树结构：``start_span`` 嵌套在当前栈顶 span 之下（如果有的话），
    否则追加到根 ``spans`` 列表。内部的 ``_span_stack`` 跟踪当前打开的 span 链。
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
        """开始一个新的 span。

        如果栈上有活跃的 span，新 span 将被追加到该 span 的 ``child_spans``；
        否则追加到追踪的顶层 ``spans`` 列表。
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
        """结束当前 span，将其从栈中弹出。

        设置 ``ended_at``、``duration_ms`` 和 ``status``。如果提供了 ``output``，
        将被截断并存储为 ``output_snapshot``。如果提供了 ``error``，将记录在
        span 上。

        返回结束的 span，若栈为空则返回 ``None``。
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
        """完成整个追踪。"""
        self.ended_at = datetime.now(UTC)
        self.duration_ms = (self.ended_at - self.started_at).total_seconds() * 1000
        self.status = status

    def to_dict(self) -> dict[str, Any]:
        """序列化为适合 JSON 传输的纯字典。"""
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


# ── 上下文传播 ──────────────────────────────────────────────────

_current_trace: ContextVar[PipelineTrace | None] = ContextVar(
    "night_diary_pipeline_trace",
    default=None,
)


def get_trace() -> PipelineTrace | None:
    """返回当前上下文的管道追踪，若没有则返回 ``None``。"""
    return _current_trace.get()


def set_trace(trace: PipelineTrace | None) -> Token[PipelineTrace | None]:
    """设置当前上下文的管道追踪。"""
    return _current_trace.set(trace)


def reset_trace(token: Token[PipelineTrace | None]) -> None:
    """使用 ``set_trace`` 返回的 token 将上下文追踪重置为先前的值。"""
    _current_trace.reset(token)


# ── 上下文管理器 ──────────────────────────────────────────────────


@contextmanager
def trace_span(
    stage_name: str,
    stage_label: str = "",
    *,
    input_snapshot: Any = None,
    metadata: dict[str, Any] | None = None,
) -> Generator[TraceSpan | None, None, None]:
    """用于追踪管道阶段的上下文管理器。

    当开发者模式关闭时（上下文中未设置 trace），产出 ``None`` 且零开销——
    不创建 span，不记录计时。

    当有活跃的追踪时，创建并产出 ``TraceSpan``。正常退出时，span 被标记为
    ``completed``。如果 ``with`` 块内发生异常，span 被标记为 ``error`` 并记录
    异常消息，然后重新抛出异常。
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
        raise
    else:
        trace.end_span(status=STATUS_COMPLETED)
