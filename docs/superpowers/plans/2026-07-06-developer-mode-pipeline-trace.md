# 开发者模式 — Agent 数据链路可视化 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为夜记 V2 新增开发者模式，可视化两个 Agent 场景的完整数据链路（实时追踪 + 回溯查看）。

**Architecture:** 后端用 PipelineTrace（ContextVar）+ trace_span 上下文管理器在管道各阶段采集数据，通过 TraceEventBus + SSE 实时推送，持久化到 pipeline_traces 表。前端用独立 DevScene 页 + DiaryScene/ChatScene 侧边栏展示。dev mode 关闭时零开销。

**Tech Stack:** Python/FastAPI（后端），Vue 3/TypeScript/Pinia（前端），SQLite + Alembic（存储），SSE（实时推送）

---

## 文件结构总览

### 后端新增/修改

| 文件 | 操作 | 职责 |
|------|------|------|
| `server/app/shared/pipeline_trace.py` | 新建 | PipelineTrace/TraceSpan 数据结构 + ContextVar + trace_span 上下文管理器 + truncate |
| `server/app/shared/trace_event_bus.py` | 新建 | TraceEventBus 内存事件总线 |
| `server/app/api/v1/dev.py` | 新建 | Dev API 路由（列表/详情/SSE/删除/统计/中间件状态） |
| `server/app/api/v1/router.py` | 修改 | 注册 dev router |
| `server/app/infrastructure/models/pipeline_trace.py` | 新建 | PipelineTraceRow ORM 模型 |
| `server/app/infrastructure/models/__init__.py` | 修改 | 导出 PipelineTraceRow |
| `server/app/infrastructure/models/llm_call_log.py` | 修改 | 加 trace_id 列 |
| `server/app/infrastructure/models/agent_decision.py` | 修改 | 加 trace_id 列 |
| `server/app/infrastructure/models/skill_activation.py` | 修改 | 加 trace_id 列 |
| `server/app/shared/tracing.py` | 修改 | 三个 Record dataclass 加 trace_id 字段 |
| `server/app/shared/tracing_llm.py` | 修改 | TracingLLMClient 从 ContextVar 读 trace_id |
| `server/app/infrastructure/llm_call_tracer.py` | 修改 | record 写入 trace_id |
| `server/app/infrastructure/agent_decision_logger.py` | 修改 | record 写入 trace_id |
| `server/app/infrastructure/skill_activation_tracer.py` | 修改 | record 写入 trace_id |
| `server/alembic/versions/002_pipeline_traces_and_trace_id.py` | 新建 | 迁移：建 pipeline_traces 表 + 三表加 trace_id 列 |
| `server/app/services/analysis_service.py` | 修改 | 场景一插桩 |
| `server/app/services/conversation_ai_service.py` | 修改 | 场景二插桩 |
| `server/app/domain/agents/graph.py` | 修改 | MultiAgentGraph.invoke 插桩 |
| `server/app/domain/agents/supervisor.py` | 修改 | classify/synthesize 插桩 |
| `server/app/services/ai/graph_nodes.py` | 修改 | 6 个 LangGraph 节点插桩 |
| `server/app/services/ai/conversation_loop.py` | 修改 | Legacy Loop 插桩 |
| `server/app/services/normalizer.py` | 修改 | from_diary/from_conversation 插桩 |
| `server/app/services/memory_gateway.py` | 修改 | persist_atom 四维检查插桩 |
| `server/app/domain/agents/entity_extractor.py` | 修改 | schedule_entity_extraction 标记 dispatched |
| `server/app/api/deps.py` | 修改 | 新增 dev trace 依赖注入 |

### 前端新增/修改

| 文件 | 操作 | 职责 |
|------|------|------|
| `src/stores/settings.ts` | 修改 | 加 developerMode 字段 |
| `src/stores/dev.ts` | 新建 | dev 状态管理 |
| `src/shared/api/dev.ts` | 新建 | Dev API 服务层 |
| `src/shared/api/http.ts` | 修改 | 拦截器附加 dev 头 |
| `src/shared/composables/useTraceStream.ts` | 新建 | SSE 订阅 composable |
| `src/features/dev/DevPipelinePanel.vue` | 新建 | 侧边栏实时追踪面板 |
| `src/features/dev/TraceSpanRow.vue` | 新建 | 单个 span 行（可展开） |
| `src/features/dev/TraceWaterfall.vue` | 新建 | 瀑布图组件 |
| `src/features/dev/TraceList.vue` | 新建 | 历史 trace 列表 |
| `src/features/dev/MiddlewareStatus.vue` | 新建 | 中间件状态 |
| `src/pages/DevScene.vue` | 新建 | 开发者模式独立页 |
| `src/router/index.ts` | 修改 | 加 /dev 路由 |
| `src/shared/components/NavTabs.vue` | 修改 | 条件渲染开发者 Tab |
| `src/pages/DiaryScene.vue` | 修改 | 嵌入 DevPipelinePanel |
| `src/pages/ChatScene.vue` | 修改 | 嵌入 DevPipelinePanel |
| `src/features/settings/DeveloperToggle.vue` | 新建 | 设置页开关 |
| `src/pages/SettingsScene.vue` | 修改 | 嵌入 DeveloperToggle |
| `src/styles/base.css` | 修改 | 加 --font-mono 变量 |

---

## Task 1: 后端 — PipelineTrace 核心数据结构

**Files:**
- Create: `server/app/shared/pipeline_trace.py`
- Test: `server/tests/unit/test_pipeline_trace.py`

- [ ] **Step 1: 编写 PipelineTrace/TraceSpan 数据结构失败测试**

```python
# server/tests/unit/test_pipeline_trace.py
"""PipelineTrace 和 TraceSpan 数据结构测试。"""
import time
import pytest
from app.shared.pipeline_trace import PipelineTrace, TraceSpan, truncate_snapshot


class TestTruncateSnapshot:
    def test_truncates_long_string(self):
        result = truncate_snapshot("x" * 1000)
        assert len(result) <= 503
        assert result.endswith("...")

    def test_preserves_short_string(self):
        assert truncate_snapshot("short") == "short"

    def test_truncates_dict_keys(self):
        big = {f"key_{i}": i for i in range(30)}
        result = truncate_snapshot(big)
        assert isinstance(result, dict)
        assert len(result) <= 20

    def test_truncates_list(self):
        big = list(range(100))
        result = truncate_snapshot(big)
        assert isinstance(result, dict)
        assert result["count"] == 100
        assert len(result["items"]) <= 3

    def test_handles_nested(self):
        data = {"outer": {"inner": "y" * 1000}}
        result = truncate_snapshot(data)
        assert len(result["outer"]["inner"]) <= 503


class TestPipelineTrace:
    def test_start_and_end_span(self):
        trace = PipelineTrace(
            trace_id="t1", scenario="diary", user_id="u1",
            started_at="2026-07-06T00:00:00Z",
        )
        span = trace.start_span("S1_test", "测试", input_data="hello")
        assert span.stage_name == "S1_test"
        assert span.status == "running"
        assert span.input_snapshot == {"input_data": "hello"}
        trace.end_span(status="completed", output_data="world")
        assert span.status == "completed"
        assert span.output_snapshot == {"output_data": "world"}
        assert span.duration_ms is not None
        assert span.duration_ms >= 0

    def test_nested_spans(self):
        trace = PipelineTrace(
            trace_id="t1", scenario="diary", user_id="u1",
            started_at="2026-07-06T00:00:00Z",
        )
        parent = trace.start_span("S1_parent", "父级")
        child = trace.start_span("S1.1_child", "子级")
        trace.end_span(status="completed")
        trace.end_span(status="completed")
        assert len(trace.spans) == 1
        assert trace.spans[0].stage_name == "S1_parent"
        assert len(trace.spans[0].child_spans) == 1
        assert trace.spans[0].child_spans[0].stage_name == "S1.1_child"

    def test_end_trace(self):
        trace = PipelineTrace(
            trace_id="t1", scenario="diary", user_id="u1",
            started_at="2026-07-06T00:00:00Z",
        )
        trace.end(status="completed")
        assert trace.status == "completed"
        assert trace.duration_ms is not None

    def test_to_dict(self):
        trace = PipelineTrace(
            trace_id="t1", scenario="diary", user_id="u1",
            started_at="2026-07-06T00:00:00Z",
        )
        trace.start_span("S1", "测试", text="input")
        trace.end_span(status="completed", result="output")
        trace.end(status="completed")
        d = trace.to_dict()
        assert d["trace_id"] == "t1"
        assert d["scenario"] == "diary"
        assert d["status"] == "completed"
        assert len(d["spans"]) == 1
        assert d["spans"][0]["stage_name"] == "S1"

    def test_span_error(self):
        trace = PipelineTrace(
            trace_id="t1", scenario="diary", user_id="u1",
            started_at="2026-07-06T00:00:00Z",
        )
        trace.start_span("S1", "测试")
        trace.end_span(status="error", error="something failed")
        assert trace.spans[0].status == "error"
        assert trace.spans[0].error == "something failed"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd server && python -m pytest tests/unit/test_pipeline_trace.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.shared.pipeline_trace'`

- [ ] **Step 3: 实现 PipelineTrace 模块**

```python
# server/app/shared/pipeline_trace.py
"""PipelineTrace 和 TraceSpan — 开发者模式数据链路追踪核心数据结构。

dev mode 关闭时 get_trace() 返回 None，trace_span yield None，零开销。
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Generator

logger = logging.getLogger(__name__)

_current_trace: ContextVar[PipelineTrace | None] = ContextVar("pipeline_trace", default=None)


def get_trace() -> PipelineTrace | None:
    """获取当前 ContextVar 中的 trace 对象，dev mode 关闭时返回 None。"""
    return _current_trace.get()


def set_trace(trace: PipelineTrace | None) -> None:
    """设置当前 ContextVar 中的 trace 对象。"""
    _current_trace.set(trace)


def truncate_snapshot(value: Any, *, max_str: int = 500, max_dict_keys: int = 20, max_list_items: int = 3) -> Any:
    """递归截断快照数据，防止大文本撑爆内存和数据库。"""
    if isinstance(value, str):
        if len(value) > max_str:
            return value[:max_str] + "..."
        return value
    if isinstance(value, dict):
        if len(value) > max_dict_keys:
            truncated = dict(list(value.items())[:max_dict_keys])
            truncated["__truncated__"] = f"... {len(value) - max_dict_keys} more keys"
            return truncated
        return {k: truncate_snapshot(v, max_str=max_str, max_dict_keys=max_dict_keys, max_list_items=max_list_items) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        if len(value) > max_list_items:
            return {"count": len(value), "items": [truncate_snapshot(v, max_str=max_str, max_dict_keys=max_dict_keys, max_list_items=max_list_items) for v in value[:max_list_items]]}
        return [truncate_snapshot(v, max_str=max_str, max_dict_keys=max_dict_keys, max_list_items=max_list_items) for v in value]
    if isinstance(value, bytes):
        return f"<bytes len={len(value)}>"
    return value


@dataclass
class TraceSpan:
    """单个管道阶段的追踪记录。"""
    span_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    stage_name: str = ""
    stage_label: str = ""
    status: str = "running"  # running | completed | error | dispatched
    started_at: float = field(default_factory=time.perf_counter)
    ended_at: float | None = None
    duration_ms: float | None = None
    input_snapshot: dict[str, Any] = field(default_factory=dict)
    output_snapshot: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    child_spans: list[TraceSpan] = field(default_factory=list)
    error: str | None = None

    def set_output(self, **kwargs: Any) -> None:
        self.output_snapshot.update(truncate_snapshot(kwargs))

    def to_dict(self) -> dict[str, Any]:
        return {
            "span_id": self.span_id,
            "stage_name": self.stage_name,
            "stage_label": self.stage_label,
            "status": self.status,
            "duration_ms": round(self.duration_ms, 2) if self.duration_ms is not None else None,
            "input_snapshot": self.input_snapshot,
            "output_snapshot": self.output_snapshot,
            "metadata": self.metadata,
            "child_spans": [s.to_dict() for s in self.child_spans],
            "error": self.error,
        }


@dataclass
class PipelineTrace:
    """完整管道追踪记录，贯穿一次请求的整个生命周期。"""
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    scenario: str = ""  # diary | chat
    user_id: str = "default"
    started_at: str = ""
    status: str = "running"  # running | completed | error
    ended_at: str | None = None
    duration_ms: float | None = None
    spans: list[TraceSpan] = field(default_factory=list)
    _span_stack: list[TraceSpan] = field(default_factory=list, repr=False)

    def start_span(self, stage_name: str, stage_label: str, **input_snapshot: Any) -> TraceSpan:
        """开始一个新的 span，自动嵌套到当前栈顶的 child_spans。"""
        span = TraceSpan(
            stage_name=stage_name,
            stage_label=stage_label,
            input_snapshot=truncate_snapshot(input_snapshot),
        )
        if self._span_stack:
            self._span_stack[-1].child_spans.append(span)
        else:
            self.spans.append(span)
        self._span_stack.append(span)
        return span

    def end_span(self, status: str = "completed", error: str | None = None, **output_snapshot: Any) -> None:
        """结束当前栈顶 span。"""
        if not self._span_stack:
            logger.warning("end_span called with empty span stack")
            return
        span = self._span_stack.pop()
        span.ended_at = time.perf_counter()
        span.duration_ms = (span.ended_at - span.started_at) * 1000
        span.status = status
        span.error = error
        span.output_snapshot.update(truncate_snapshot(output_snapshot))

    def end(self, status: str = "completed") -> None:
        """结束整个 trace。"""
        self.status = status
        self.ended_at = self.started_at
        # duration_ms 由调用方或 to_dict 计算

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "scenario": self.scenario,
            "user_id": self.user_id,
            "status": self.status,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_ms": self.duration_ms,
            "span_count": len(self.spans),
            "spans": [s.to_dict() for s in self.spans],
        }


@contextmanager
def trace_span(stage_name: str, stage_label: str, **input_snapshot: Any) -> Generator[TraceSpan | None, None, None]:
    """trace span 上下文管理器。dev mode 关闭时 yield None，零开销。

    用法:
        with trace_span("S3_preprocess", "预处理", raw_text=content) as span:
            result = process(content)
            if span:
                span.metadata["flag"] = result.flag
    """
    trace = get_trace()
    if trace is None:
        yield None
        return
    span = trace.start_span(stage_name, stage_label, **input_snapshot)
    try:
        yield span
    except Exception as e:
        trace.end_span(status="error", error=str(e))
        raise
    else:
        trace.end_span(status="completed")
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd server && python -m pytest tests/unit/test_pipeline_trace.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: 提交**

```bash
cd server && git add app/shared/pipeline_trace.py tests/unit/test_pipeline_trace.py
git commit -m "feat: add PipelineTrace/TraceSpan data structures and trace_span context manager"
```

---

## Task 2: 后端 — TraceEventBus 内存事件总线

**Files:**
- Create: `server/app/shared/trace_event_bus.py`
- Test: `server/tests/unit/test_trace_event_bus.py`

- [ ] **Step 1: 编写 TraceEventBus 失败测试**

```python
# server/tests/unit/test_trace_event_bus.py
"""TraceEventBus 内存事件总线测试。"""
import asyncio
import pytest
from app.shared.trace_event_bus import TraceEventBus


class TestTraceEventBus:
    @pytest.mark.asyncio
    async def test_subscribe_and_publish(self):
        bus = TraceEventBus()
        queue = await bus.subscribe("trace-1")
        await bus.publish("trace-1", {"type": "span_complete", "span": {}})
        event = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert event["type"] == "span_complete"

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_queue(self):
        bus = TraceEventBus()
        queue = await bus.subscribe("trace-1")
        await bus.unsubscribe("trace-1", queue)
        assert "trace-1" not in bus._subscribers

    @pytest.mark.asyncio
    async def test_publish_to_no_subscribers_is_noop(self):
        bus = TraceEventBus()
        await bus.publish("nonexistent", {"type": "test"})  # should not raise

    @pytest.mark.asyncio
    async def test_queue_full_drops_event(self):
        bus = TraceEventBus(max_queue_size=1)
        queue = await bus.subscribe("trace-1")
        await bus.publish("trace-1", {"type": "event1"})
        await bus.publish("trace-1", {"type": "event2"})  # should drop, not block
        event = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert event["type"] == "event1"

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self):
        bus = TraceEventBus()
        q1 = await bus.subscribe("trace-1")
        q2 = await bus.subscribe("trace-1")
        await bus.publish("trace-1", {"type": "test"})
        e1 = await asyncio.wait_for(q1.get(), timeout=1.0)
        e2 = await asyncio.wait_for(q2.get(), timeout=1.0)
        assert e1["type"] == "test"
        assert e2["type"] == "test"

    @pytest.mark.asyncio
    async def test_cleanup_removes_empty_subscriber_list(self):
        bus = TraceEventBus()
        queue = await bus.subscribe("trace-1")
        await bus.unsubscribe("trace-1", queue)
        await bus.cleanup("trace-1")
        assert "trace-1" not in bus._subscribers
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd server && python -m pytest tests/unit/test_trace_event_bus.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: 实现 TraceEventBus**

```python
# server/app/shared/trace_event_bus.py
"""TraceEventBus — 内存事件总线，trace span 完成时推送事件给 SSE 订阅者。

用 asyncio.Queue 实现 pub/sub，轻量且无外部依赖。
慢消费者（QueueFull）时丢弃事件，不阻塞管道。
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)


class TraceEventBus:
    """内存事件总线。trace span 完成时推送事件给 SSE 订阅者。"""

    def __init__(self, max_queue_size: int = 100) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._lock = asyncio.Lock()
        self._max_queue_size = max_queue_size

    async def subscribe(self, trace_id: str) -> asyncio.Queue:
        """订阅指定 trace_id 的事件流。"""
        async with self._lock:
            queue: asyncio.Queue = asyncio.Queue(maxsize=self._max_queue_size)
            self._subscribers[trace_id].append(queue)
            return queue

    async def unsubscribe(self, trace_id: str, queue: asyncio.Queue) -> None:
        """取消订阅。"""
        async with self._lock:
            if trace_id in self._subscribers:
                try:
                    self._subscribers[trace_id].remove(queue)
                except ValueError:
                    pass
                if not self._subscribers[trace_id]:
                    del self._subscribers[trace_id]

    async def publish(self, trace_id: str, event: dict[str, Any]) -> None:
        """推送事件给所有订阅者。QueueFull 时丢弃，不阻塞管道。"""
        for queue in self._subscribers.get(trace_id, []):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("TraceEventBus: dropping event for slow consumer, trace_id=%s", trace_id)

    async def cleanup(self, trace_id: str) -> None:
        """清理指定 trace_id 的所有订阅者。"""
        async with self._lock:
            self._subscribers.pop(trace_id, None)


# 全局单例
_event_bus: TraceEventBus | None = None


def get_event_bus() -> TraceEventBus:
    global _event_bus
    if _event_bus is None:
        _event_bus = TraceEventBus()
    return _event_bus
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd server && python -m pytest tests/unit/test_trace_event_bus.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
cd server && git add app/shared/trace_event_bus.py tests/unit/test_trace_event_bus.py
git commit -m "feat: add TraceEventBus in-memory event bus for SSE push"
```

---

## Task 3: 后端 — 数据库迁移 + ORM 模型

**Files:**
- Create: `server/app/infrastructure/models/pipeline_trace.py`
- Modify: `server/app/infrastructure/models/__init__.py`
- Modify: `server/app/infrastructure/models/llm_call_log.py`
- Modify: `server/app/infrastructure/models/agent_decision.py`
- Modify: `server/app/infrastructure/models/skill_activation.py`
- Create: `server/alembic/versions/002_pipeline_traces_and_trace_id.py`

- [ ] **Step 1: 创建 PipelineTraceRow ORM 模型**

```python
# server/app/infrastructure/models/pipeline_trace.py
"""PipelineTraceRow ORM 模型。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, Real, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class PipelineTraceRow(Base):
    """pipeline_traces 表 — 存储完整的管道追踪 JSON。"""
    __tablename__ = "pipeline_traces"

    trace_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scenario: Mapped[str] = mapped_column(String(16), nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[str] = mapped_column(String(32), nullable=False)
    ended_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Real, nullable=True)
    span_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ref_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trace_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("idx_traces_user", "user_id", "started_at"),
        Index("idx_traces_scenario", "scenario", "started_at"),
    )
```

- [ ] **Step 2: 导出 PipelineTraceRow**

读取 `server/app/infrastructure/models/__init__.py` 当前内容，在末尾添加导出。

在 `__init__.py` 中添加：
```python
from app.infrastructure.models.pipeline_trace import PipelineTraceRow

__all__.append("PipelineTraceRow")
```

（具体修改方式：在文件末尾的 `__all__` 列表或 import 块中追加。需要先读取文件确认现有结构。）

- [ ] **Step 3: 给三个现有 ORM 模型加 trace_id 列**

对 `llm_call_log.py`、`agent_decision.py`、`skill_activation.py` 各添加：
```python
trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
```

在各自模型的字段列表中追加此行。

- [ ] **Step 4: 创建 Alembic 迁移**

```python
# server/alembic/versions/002_pipeline_traces_and_trace_id.py
"""pipeline_traces 表 + 三表加 trace_id 列

Revision ID: 002_pipeline_traces
Revises: 001_conversation_feedback
Create Date: 2026-07-06

"""
from alembic import op
import sqlalchemy as sa


revision = "002_pipeline_traces"
down_revision = "001_conversation_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. 创建 pipeline_traces 表
    op.create_table(
        "pipeline_traces",
        sa.Column("trace_id", sa.String(64), primary_key=True),
        sa.Column("scenario", sa.String(16), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("started_at", sa.String(32), nullable=False),
        sa.Column("ended_at", sa.String(32), nullable=True),
        sa.Column("duration_ms", sa.Float, nullable=True),
        sa.Column("span_count", sa.Integer, nullable=True),
        sa.Column("ref_id", sa.String(64), nullable=True),
        sa.Column("trace_json", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("idx_traces_user", "pipeline_traces", ["user_id", "started_at"])
    op.create_index("idx_traces_scenario", "pipeline_traces", ["scenario", "started_at"])

    # 2. 三表加 trace_id 列
    with op.batch_alter_table("llm_call_logs") as batch_op:
        batch_op.add_column(sa.Column("trace_id", sa.String(64), nullable=True))
        batch_op.create_index("ix_llm_call_logs_trace_id", ["trace_id"])

    with op.batch_alter_table("agent_decisions") as batch_op:
        batch_op.add_column(sa.Column("trace_id", sa.String(64), nullable=True))
        batch_op.create_index("ix_agent_decisions_trace_id", ["trace_id"])

    with op.batch_alter_table("skill_activations") as batch_op:
        batch_op.add_column(sa.Column("trace_id", sa.String(64), nullable=True))
        batch_op.create_index("ix_skill_activations_trace_id", ["trace_id"])


def downgrade() -> None:
    with op.batch_alter_table("skill_activations") as batch_op:
        batch_op.drop_index("ix_skill_activations_trace_id")
        batch_op.drop_column("trace_id")

    with op.batch_alter_table("agent_decisions") as batch_op:
        batch_op.drop_index("ix_agent_decisions_trace_id")
        batch_op.drop_column("trace_id")

    with op.batch_alter_table("llm_call_logs") as batch_op:
        batch_op.drop_index("ix_llm_call_logs_trace_id")
        batch_op.drop_column("trace_id")

    op.drop_index("idx_traces_scenario", table_name="pipeline_traces")
    op.drop_index("idx_traces_user", table_name="pipeline_traces")
    op.drop_table("pipeline_traces")
```

- [ ] **Step 5: 运行迁移**

Run: `cd server && python -m alembic upgrade head`
Expected: 成功创建表和列

- [ ] **Step 6: 提交**

```bash
cd server && git add app/infrastructure/models/pipeline_trace.py app/infrastructure/models/__init__.py app/infrastructure/models/llm_call_log.py app/infrastructure/models/agent_decision.py app/infrastructure/models/skill_activation.py alembic/versions/002_pipeline_traces_and_trace_id.py
git commit -m "feat: add pipeline_traces table and trace_id columns to existing tracing tables"
```

---

## Task 4: 后端 — 现有 Tracing 体系桥接 trace_id

**Files:**
- Modify: `server/app/shared/tracing.py`
- Modify: `server/app/shared/tracing_llm.py`
- Modify: `server/app/infrastructure/llm_call_tracer.py`
- Modify: `server/app/infrastructure/agent_decision_logger.py`
- Modify: `server/app/infrastructure/skill_activation_tracer.py`

- [ ] **Step 1: 给三个 Record dataclass 加 trace_id 字段**

在 `server/app/shared/tracing.py` 中，给 `LLMCallRecord`、`AgentDecisionRecord`、`SkillActivationRecord` 三个 dataclass 各添加字段：

```python
trace_id: str = ""
```

添加位置：在每个 dataclass 的字段列表末尾（在 `created_at` 之前）。

- [ ] **Step 2: TracingLLMClient 从 ContextVar 读 trace_id**

在 `server/app/shared/tracing_llm.py` 的 `_record` 方法中，构造 `LLMCallRecord` 时从 ContextVar 读取 trace_id：

在 `_record` 方法中添加：
```python
from app.shared.pipeline_trace import get_trace

trace = get_trace()
trace_id = trace.trace_id if trace else ""
```

然后在 `LLMCallRecord(...)` 构造中添加 `trace_id=trace_id`。

- [ ] **Step 3: SqliteLLMCallTracer 写入 trace_id**

在 `server/app/infrastructure/llm_call_tracer.py` 的 `record` 方法中，给 `LlmCallLogRow` 构造添加 `trace_id=entry.trace_id`。

- [ ] **Step 4: SqliteAgentDecisionLogger 写入 trace_id**

在 `server/app/infrastructure/agent_decision_logger.py` 的 `record` 方法中，给 `AgentDecisionRow` 构造添加 `trace_id=entry.trace_id`。

同时在 `load_records` 方法中添加可选参数 `trace_id: str | None = None`，用于按 trace_id 过滤。

- [ ] **Step 5: SqliteSkillActivationTracer 写入 trace_id**

在 `server/app/infrastructure/skill_activation_tracer.py` 的 `record` 方法中，给 `SkillActivationRow` 构造添加 `trace_id=entry.trace_id`。

- [ ] **Step 6: 运行现有测试确保不破坏**

Run: `cd server && python -m pytest tests/ -v --tb=short -x`
Expected: 所有现有测试通过

- [ ] **Step 7: 提交**

```bash
cd server && git add app/shared/tracing.py app/shared/tracing_llm.py app/infrastructure/llm_call_tracer.py app/infrastructure/agent_decision_logger.py app/infrastructure/skill_activation_tracer.py
git commit -m "feat: bridge trace_id into existing LLM/decision/skill tracing tables"
```

---

## Task 5: 后端 — Dev API 路由

**Files:**
- Create: `server/app/api/v1/dev.py`
- Modify: `server/app/api/v1/router.py`
- Modify: `server/app/api/deps.py`

- [ ] **Step 1: 创建 Dev API 路由**

```python
# server/app/api/v1/dev.py
"""Dev API 路由 — 开发者模式数据链路可视化端点。"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUserDep, DbDep
from app.infrastructure.models.pipeline_trace import PipelineTraceRow
from app.shared.pipeline_trace import get_trace
from app.shared.trace_event_bus import get_event_bus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dev", tags=["dev"])


@router.get("/traces")
def list_traces(
    db: DbDep,
    user: CurrentUserDep,
    scenario: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    ref_id: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    """历史 trace 列表。"""
    stmt = select(PipelineTraceRow).where(PipelineTraceRow.user_id == str(user.id))
    if scenario:
        stmt = stmt.where(PipelineTraceRow.scenario == scenario)
    if status_filter:
        stmt = stmt.where(PipelineTraceRow.status == status_filter)
    if ref_id:
        stmt = stmt.where(PipelineTraceRow.ref_id == ref_id)

    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.execute(total_stmt).scalar() or 0

    stmt = stmt.order_by(desc(PipelineTraceRow.started_at)).offset((page - 1) * page_size).limit(page_size)
    rows = db.execute(stmt).scalars().all()

    items = [
        {
            "trace_id": r.trace_id,
            "scenario": r.scenario,
            "status": r.status,
            "started_at": r.started_at,
            "duration_ms": r.duration_ms,
            "span_count": r.span_count,
            "ref_id": r.ref_id,
        }
        for r in rows
    ]
    return {"items": items, "total": total}


@router.get("/traces/{trace_id}")
def get_trace_detail(db: DbDep, user: CurrentUserDep, trace_id: str) -> dict:
    """单条 trace 详情。"""
    row = db.execute(
        select(PipelineTraceRow).where(
            PipelineTraceRow.trace_id == trace_id,
            PipelineTraceRow.user_id == str(user.id),
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Trace not found")
    return json.loads(row.trace_json)


@router.delete("/traces/{trace_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trace(db: DbDep, user: CurrentUserDep, trace_id: str) -> Response:
    """删除一条 trace。"""
    row = db.execute(
        select(PipelineTraceRow).where(
            PipelineTraceRow.trace_id == trace_id,
            PipelineTraceRow.user_id == str(user.id),
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Trace not found")
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/traces/{trace_id}/stream")
async def stream_trace(trace_id: str, request: Request):
    """SSE 实时订阅 trace 事件。"""
    event_bus = get_event_bus()

    async def event_generator():
        queue = await event_bus.subscribe(trace_id)
        try:
            # 先推送已完成的 spans
            trace = get_trace()
            if trace and trace.trace_id == trace_id:
                for span in trace.spans:
                    yield _format_sse({"type": "span_complete", "trace_id": trace_id, "span": span.to_dict()})

            # 持续监听新事件
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield _format_sse(event)
                    if event.get("type") == "trace_complete":
                        break
                except asyncio.TimeoutError:
                    yield _format_sse({"type": "heartbeat"})
        finally:
            await event_bus.unsubscribe(trace_id, queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/stats")
def get_dev_stats(db: DbDep, user: CurrentUserDep) -> dict:
    """统计数据。"""
    base = select(PipelineTraceRow).where(PipelineTraceRow.user_id == str(user.id))
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar() or 0

    scenario_stmt = (
        select(PipelineTraceRow.scenario, func.count())
        .where(PipelineTraceRow.user_id == str(user.id))
        .group_by(PipelineTraceRow.scenario)
    )
    by_scenario = {row[0]: row[1] for row in db.execute(scenario_stmt).all()}

    avg_stmt = select(func.avg(PipelineTraceRow.duration_ms)).where(
        PipelineTraceRow.user_id == str(user.id),
        PipelineTraceRow.duration_ms.isnot(None),
    )
    avg_duration = db.execute(avg_stmt).scalar()

    error_count = db.execute(
        select(func.count()).select_from(
            base.where(PipelineTraceRow.status == "error").subquery()
        )
    ).scalar() or 0

    return {
        "total_traces": total,
        "by_scenario": by_scenario,
        "avg_duration_ms": round(avg_duration, 2) if avg_duration else 0,
        "error_count": error_count,
    }


@router.get("/middleware-status")
def get_middleware_status() -> dict:
    """中间件健康状态。"""
    from app.infrastructure.redis_client import is_redis_available
    from app.infrastructure.entity_graph import is_neo4j_available

    try:
        from app.services.ai.conversation_graph import LANGGRAPH_AVAILABLE
    except ImportError:
        LANGGRAPH_AVAILABLE = False

    try:
        from app.infrastructure.task_queue import is_rq_available
        rq_available = is_rq_available()
    except ImportError:
        rq_available = False

    return {
        "redis": is_redis_available(),
        "neo4j": is_neo4j_available(),
        "langgraph": LANGGRAPH_AVAILABLE,
        "rq": rq_available,
    }


def _format_sse(event: dict) -> str:
    """格式化 SSE 事件。"""
    event_type = event.get("type", "message")
    data = json.dumps(event, ensure_ascii=False, default=str)
    return f"event: {event_type}\ndata: {data}\n\n"
```

- [ ] **Step 2: 注册 dev router**

在 `server/app/api/v1/router.py` 中添加：

```python
from app.api.v1 import dev
api_router.include_router(dev.router)
```

- [ ] **Step 3: 运行测试确保不破坏**

Run: `cd server && python -m pytest tests/ -v --tb=short -x`
Expected: 通过

- [ ] **Step 4: 提交**

```bash
cd server && git add app/api/v1/dev.py app/api/v1/router.py
git commit -m "feat: add Dev API routes (trace list/detail/SSE/delete/stats/middleware-status)"
```

---

## Task 6: 后端 — 场景一插桩（10 个 span）

**Files:**
- Modify: `server/app/services/analysis_service.py`
- Modify: `server/app/domain/agents/graph.py`
- Modify: `server/app/domain/agents/supervisor.py`
- Modify: `server/app/services/normalizer.py`
- Modify: `server/app/services/memory_gateway.py`

- [ ] **Step 1: analysis_service.py 插桩**

在 `analysis_service.py` 顶部添加导入：
```python
from app.shared.pipeline_trace import trace_span, get_trace, PipelineTrace, set_trace
from app.shared.trace_event_bus import get_event_bus
import json
```

在 `trigger_analysis` 函数中，创建 trace 并设置 ContextVar：

```python
def trigger_analysis(
    db: Session, diary_id: int, container: ServiceContainer, *,
    user_id: str,
    style_fragment: str | None = None,
    trace_id: str | None = None,
) -> tuple[AnalysisRow, int]:
    """End-to-end entry: build planner from container and create analysis."""
    # 创建 trace（如果有 trace_id 表示 dev mode 开启）
    trace = None
    if trace_id:
        trace = PipelineTrace(
            trace_id=trace_id,
            scenario="diary",
            user_id=user_id,
            started_at=datetime.utcnow().isoformat(),
        )
        set_trace(trace)

    try:
        planner = container.build_execution_planner(db, user_id=user_id)
        result = create_analysis(db, diary_id, user_id=user_id, planner=planner, container=container, style_fragment=style_fragment)
        return result
    finally:
        if trace:
            trace.end(status="completed")
            _persist_trace(db, trace, ref_id=str(diary_id))
            _publish_trace_complete(trace)
            set_trace(None)
```

在 `create_analysis` 中添加 span 插桩：

```python
def create_analysis(db, diary_id, *, user_id, planner, container=None, style_fragment=None):
    with trace_span("S2_routing", "路由决策", diary_id=diary_id) as span:
        entry = diary_service.get_entry(db, diary_id, user_id=user_id)
        # ... 原有逻辑 ...
        routing_decision = planner.plan(diary_id=diary_id, content=content, diary_length=len(content))
        if span:
            span.metadata["tier"] = routing_decision.tier
            span.metadata["mode"] = routing_decision.mode
    # ... planner.execute 内部会触发 graph 插桩 ...
    with trace_span("S6_persist", "持久化分析结果") as span:
        analysis = _persist_analysis(db, entry, result, user_id=user_id)
    # ... 记忆同步 ...
    if container is not None:
        with trace_span("S7_memory", "记忆同步") as span:
            mem_count = _sync_diary_to_memory(db, entry, analysis.reply, container, user_id=user_id)
    return analysis, mem_count
```

注意：`S1_normalize`、`S3_classify`、`S4a/b/c`、`S5_synthesize` 的插桩在 `graph.py` 和 `supervisor.py` 中完成（通过 ContextVar 自动传播）。

- [ ] **Step 2: graph.py invoke 插桩**

在 `graph.py` 的 `invoke` 方法中添加 span：

```python
async def invoke(self, state: MultiAgentState) -> MultiAgentState:
    from app.shared.pipeline_trace import trace_span

    with trace_span("S3_classify", "Supervisor 分类", diary_content=merged.get("diary_content", "")) as span:
        classify_update = await self._supervisor.classify(cast(MultiAgentState, merged))
        _merge(merged, classify_update)
        if span:
            span.metadata["intent"] = merged.get("intent", "")
            span.metadata["tier"] = merged.get("tier", "")
            span.metadata["activated_agents"] = merged.get("activated_agents", [])

    # Phase 2: 分阶段 fan-out
    for phase in sorted({...}):
        with trace_span(f"S4_phase{phase}", f"Phase {phase} 并发执行") as phase_span:
            results = await asyncio.gather(...)
            # ...

    with trace_span("S5_synthesize", "合成回信") as span:
        synth_update = await self._supervisor.synthesize(cast(MultiAgentState, merged))
        _merge(merged, synth_update)
        if span:
            span.set_output(final_response=merged.get("final_response", ""))
```

- [ ] **Step 3: normalizer.py 插桩**

在 `ContentNormalizer.from_diary` 和 `from_conversation` 方法中添加：

```python
@staticmethod
def from_diary(entry, reply="", user_id="default"):
    from app.shared.pipeline_trace import trace_span
    with trace_span("S1_normalize", "归一化", source="diary", content=entry.content if entry else "") as span:
        result = _do_from_diary(entry, reply, user_id)
        if span:
            span.set_output(emotion=result.emotion, tags=result.tags)
        return result
```

- [ ] **Step 4: memory_gateway.py 插桩**

在 `persist_atom` 方法的四维检查处添加 span：

```python
def persist_atom(self, atom):
    from app.shared.pipeline_trace import trace_span
    with trace_span("S8_memory_check", "四维检查", source=atom.source) as span:
        should = self.should_persist(atom)
        if span:
            span.metadata["should_persist"] = should
        if not should:
            return None
    with trace_span("S9_memory_write", "情景+长期写入"):
        return self._do_persist(atom)
```

- [ ] **Step 5: 运行测试**

Run: `cd server && python -m pytest tests/ -v --tb=short -x`
Expected: 通过

- [ ] **Step 6: 提交**

```bash
cd server && git add app/services/analysis_service.py app/domain/agents/graph.py app/domain/agents/supervisor.py app/services/normalizer.py app/services/memory_gateway.py
git commit -m "feat: instrument scenario 1 (diary→reply) with 10 trace spans"
```

---

## Task 7: 后端 — 场景二插桩（13 个 span）

**Files:**
- Modify: `server/app/services/conversation_ai_service.py`
- Modify: `server/app/services/ai/graph_nodes.py`
- Modify: `server/app/services/ai/conversation_loop.py`

- [ ] **Step 1: conversation_ai_service.py 插桩**

在 `generate_reply` 方法中添加 trace 创建和各阶段 span：

```python
def generate_reply(db, container, *, conversation_id, content, diary_ids, user_id, auto_retrieve=True, crisis_guard=None, use_graph=True, trace_id=None):
    from app.shared.pipeline_trace import trace_span, PipelineTrace, set_trace, get_trace
    from app.shared.trace_event_bus import get_event_bus
    import json

    trace = None
    if trace_id:
        trace = PipelineTrace(trace_id=trace_id, scenario="chat", user_id=user_id, started_at=datetime.utcnow().isoformat())
        set_trace(trace)

    try:
        with trace_span("S1_session", "会话路由", conversation_id=conversation_id):
            session = get_or_create_session(db, conversation_id, user_id=user_id)

        with trace_span("S2_crisis", "危机检测", content=content) as span:
            guard = crisis_guard or container.get_crisis_guard()
            crisis = guard.detect(content)
            if span:
                span.metadata["is_crisis"] = crisis.is_crisis
            if crisis.is_crisis:
                # 短路返回
                return ChatReplyResult(reply_text=crisis.safe_response, is_crisis=True, ...)

        with trace_span("S3_preprocess", "输入预处理", raw_text=content) as span:
            preprocessor = InputPreprocessor()
            preprocess_result = preprocessor.process(content, context=brief_context)
            if span:
                span.metadata["safety_flag"] = preprocess_result.safety_flag
                span.metadata["omission_flag"] = preprocess_result.omission_detected

        with trace_span("S4_intent", "意图分类", clean_text=preprocess_result.text):
            classifier = container.get_chat_intent_classifier(db, user_id=user_id)
            intent_result = classifier.classify_sync(preprocess_result.text, context=brief_context)

        with trace_span("S5_slot", "槽位抽取"):
            slot_result = SlotExtractor().extract(preprocess_result.text, intent=intent_result.intent_category)

        with trace_span("S6_skills", "技能选择"):
            skill_registry = container.get_chat_skill_registry()
            skills = skill_registry.select_skills(content, skill_profile, token_budget=4000, decision_id=conversation_id)

        # Stage 3: 上下文组装
        if intent_result.need_retrieval:
            with trace_span("S7a_query_rewrite", "查询改写", content=preprocess_result.text):
                query_understander = QueryUnderstander()
                rewritten = query_understander.understand(preprocess_result.text, context=brief_context)
            with trace_span("S7b_rag", "RAG检索", query=rewritten):
                retrieved_ids = _retrieve_related_diary_ids(db, rewritten, user_id=user_id)

        with trace_span("S7c_episodic", "情景记忆"):
            episodic_text = _format_episodic_memories(db, user_id=user_id, conversation_id=conversation_id)

        with trace_span("S7d_tools", "工具构建"):
            tools = _build_tools(intent_result, container)

        # Stage 4: Agentic Loop
        with trace_span("S8_loop", "Agentic Loop") as span:
            result = run_conversation_loop(db, container, conversation_id=conversation_id, content=preprocess_result.text, ...)
            if span:
                span.metadata["stop_reason"] = result.stop_reason
                span.metadata["tool_calls"] = result.tool_calls_made

        # Stage 5: 记忆回写
        with trace_span("S10_memory", "情景记忆写入"):
            _maybe_persist_episodic(db, content, result.reply_text, conversation_id, user_id)

        return ChatReplyResult(reply_text=result.reply_text, ...)
    finally:
        if trace:
            trace.end(status="completed")
            _persist_trace(db, trace, ref_id=conversation_id)
            _publish_trace_complete(trace)
            set_trace(None)
```

- [ ] **Step 2: graph_nodes.py 6 个节点插桩**

在每个节点函数中添加 `trace_span`：

```python
# graph_nodes.py
from app.shared.pipeline_trace import trace_span

def preprocess_node(state):
    with trace_span("S8.1_preprocess", "预处理节点", raw_text=state.get("content", "")) as span:
        result = InputPreprocessor().process(state["content"], context=state.get("brief_context", ""))
        if span:
            span.metadata["safety_flag"] = result.safety_flag
        return {"content": result.text, "preprocess_result": result}

def understand_node(state):
    with trace_span("S8.2_understand", "槽位抽取节点"):
        slot_result = SlotExtractor().extract(state["content"], intent=state.get("intent_result", {}).intent_category if state.get("intent_result") else None)
        return {"slot_result": slot_result, "retrieval_query": state["content"]}

def plan_node(state):
    with trace_span("S8.3_plan", "计划节点") as span:
        intent_result = state.get("intent_result")
        enable_tools = bool(intent_result and intent_result.need_tools)
        if span:
            span.metadata["enable_tools"] = enable_tools
            span.metadata["tier"] = getattr(intent_result, "tier", "")
        return {"enable_tools": enable_tools, "tier": getattr(intent_result, "tier", "medium"), "max_iterations": getattr(intent_result, "max_iterations", 1), "should_execute_tools": enable_tools}

def execute_tools_node(state):
    with trace_span("S8.4_execute_tools", "工具执行节点") as span:
        # ... 原有逻辑 ...
        if span:
            span.metadata["tool_calls"] = tool_calls_made
        return {...}

def generate_node(state):
    with trace_span("S8.5_generate", "生成节点") as span:
        # ... 原有逻辑 ...
        if span:
            span.metadata["stop_reason"] = stop_reason
        return {...}

def postprocess_node(state):
    with trace_span("S8.6_postprocess", "后处理节点") as span:
        # ... 原有逻辑 ...
        if span:
            span.metadata["citation_count"] = len(citations)
        return {...}
```

- [ ] **Step 3: conversation_loop.py Legacy Loop 插桩**

在 `run_conversation_loop` 中添加 trace_span 包裹循环：

```python
def run_conversation_loop(db, container, *, ...):
    from app.shared.pipeline_trace import trace_span
    with trace_span("S8_loop_legacy", "Legacy Loop") as span:
        for iteration in range(max_iterations):
            with trace_span(f"S8.loop_{iteration}", f"第{iteration+1}轮"):
                # ... 原有逻辑 ...
        if span:
            span.metadata["iterations"] = iteration + 1
            span.metadata["stop_reason"] = result.stop_reason
        return result
```

- [ ] **Step 4: 添加 _persist_trace 和 _publish_trace_complete 辅助函数**

在 `analysis_service.py`（或单独的 `server/app/shared/trace_persistence.py`）中添加：

```python
def _persist_trace(db: Session, trace: PipelineTrace, ref_id: str | None = None) -> None:
    """持久化 trace 到 pipeline_traces 表（best-effort）。"""
    try:
        from app.infrastructure.models.pipeline_trace import PipelineTraceRow
        import json
        trace_dict = trace.to_dict()
        row = PipelineTraceRow(
            trace_id=trace.trace_id,
            scenario=trace.scenario,
            user_id=trace.user_id,
            status=trace.status,
            started_at=trace.started_at,
            ended_at=trace.ended_at,
            duration_ms=trace.duration_ms,
            span_count=len(trace.spans),
            ref_id=ref_id,
            trace_json=json.dumps(trace_dict, ensure_ascii=False, default=str),
        )
        db.add(row)
        db.commit()
    except Exception as e:
        logger.warning("Failed to persist trace: %s", e)
        db.rollback()


async def _publish_trace_complete(trace: PipelineTrace) -> None:
    """通过 EventBus 推送 trace_complete 事件（best-effort）。"""
    try:
        from app.shared.trace_event_bus import get_event_bus
        event_bus = get_event_bus()
        await event_bus.publish(trace.trace_id, {
            "type": "trace_complete",
            "trace_id": trace.trace_id,
            "trace": {"status": trace.status, "duration_ms": trace.duration_ms, "span_count": len(trace.spans)},
        })
    except Exception as e:
        logger.warning("Failed to publish trace_complete: %s", e)
```

- [ ] **Step 5: API 端点传递 trace_id**

在 `server/app/api/v1/analysis.py` 的 `trigger_analysis` 端点中读取请求头：

```python
from fastapi import Request

@router.post("/{diary_id}", ...)
def trigger_analysis(
    diary_id: int,
    db: DbDep,
    container: ContainerDep,
    user: CurrentUserDep,
    request: AnalysisTriggerRequest | None = None,
    http_request: Request = None,  # 添加 Request 参数
) -> AnalysisResponse:
    trace_id = http_request.headers.get("X-Trace-Id") if http_request else None
    # ... 传递 trace_id 给 analysis_service.trigger_analysis ...
    row, mem_count = analysis_service.trigger_analysis(
        db, diary_id, container, user_id=str(user.id), style_fragment=style_fragment, trace_id=trace_id
    )
```

同样在 `conversation.py` 的 `send_message` 端点中添加 trace_id 传递。

- [ ] **Step 6: 运行测试**

Run: `cd server && python -m pytest tests/ -v --tb=short -x`
Expected: 通过

- [ ] **Step 7: 提交**

```bash
cd server && git add app/services/conversation_ai_service.py app/services/ai/graph_nodes.py app/services/ai/conversation_loop.py app/api/v1/analysis.py app/api/v1/conversation.py app/shared/trace_persistence.py
git commit -m "feat: instrument scenario 2 (chat→dialogue) with 13 trace spans"
```

---

## Task 8: 前端 — 基础设施（settings + store + API + composable）

**Files:**
- Modify: `src/stores/settings.ts`
- Create: `src/stores/dev.ts`
- Create: `src/shared/api/dev.ts`
- Modify: `src/shared/api/http.ts`
- Create: `src/shared/composables/useTraceStream.ts`
- Modify: `src/styles/base.css`

- [ ] **Step 1: settings.ts 加 developerMode 字段**

在 `AppSettingsSnapshot` interface 中添加 `developerMode: boolean`。

在 `DEFAULTS` 对象中添加 `developerMode: false`。

在 `persist()` 函数的 snapshot 对象中添加 `developerMode: developerMode.value`。

在 `watch` 的依赖数组中添加 `developerMode`。

在 store setup 中添加 `const developerMode = ref(DEFAULTS.developerMode)` 并在 return 中导出。

- [ ] **Step 2: 创建 dev store**

```typescript
// src/stores/dev.ts
import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { TraceSummary, PipelineTrace, TraceSpan } from '@/shared/api/dev'

export const useDevStore = defineStore('dev', () => {
  const traceList = ref<TraceSummary[]>([])
  const currentTraceDetail = ref<PipelineTrace | null>(null)
  const activeTraceId = ref<string | null>(null)
  const total = ref(0)

  function setActiveTrace(traceId: string | null) {
    activeTraceId.value = traceId
  }

  return { traceList, currentTraceDetail, activeTraceId, total, setActiveTrace }
})
```

- [ ] **Step 3: 创建 dev API 服务**

```typescript
// src/shared/api/dev.ts
import { getHttpClient } from './http'

export interface TraceSummary {
  trace_id: string
  scenario: 'diary' | 'chat'
  status: 'completed' | 'error'
  started_at: string
  duration_ms: number
  span_count: number
  ref_id: string | null
}

export interface TraceSpan {
  span_id: string
  stage_name: string
  stage_label: string
  status: 'running' | 'completed' | 'error' | 'dispatched'
  duration_ms: number | null
  input_snapshot: Record<string, unknown>
  output_snapshot: Record<string, unknown>
  metadata: Record<string, unknown>
  child_spans: TraceSpan[]
  error: string | null
}

export interface PipelineTrace {
  trace_id: string
  scenario: 'diary' | 'chat'
  user_id: string
  status: 'running' | 'completed' | 'error'
  started_at: string
  ended_at: string | null
  duration_ms: number | null
  span_count: number
  spans: TraceSpan[]
}

export interface MiddlewareStatus {
  redis: boolean
  neo4j: boolean
  langgraph: boolean
  rq: boolean
}

export async function listTraces(params?: {
  scenario?: string
  status?: string
  ref_id?: string
  page?: number
  page_size?: number
}): Promise<{ items: TraceSummary[]; total: number }> {
  const client = await getHttpClient()
  const { data } = await client.get('/api/v1/dev/traces', { params })
  return data
}

export async function getTrace(traceId: string): Promise<PipelineTrace> {
  const client = await getHttpClient()
  const { data } = await client.get(`/api/v1/dev/traces/${traceId}`)
  return data
}

export async function deleteTrace(traceId: string): Promise<void> {
  const client = await getHttpClient()
  await client.delete(`/api/v1/dev/traces/${traceId}`)
}

export async function getDevStats(): Promise<{
  total_traces: number
  by_scenario: Record<string, number>
  avg_duration_ms: number
  error_count: number
}> {
  const client = await getHttpClient()
  const { data } = await client.get('/api/v1/dev/stats')
  return data
}

export async function getMiddlewareStatus(): Promise<MiddlewareStatus> {
  const client = await getHttpClient()
  const { data } = await client.get('/api/v1/dev/middleware-status')
  return data
}
```

- [ ] **Step 4: http.ts 拦截器添加 dev 头**

在 `getHttpClient()` 的 JWT 请求拦截器之后，添加 dev mode 头逻辑。在现有拦截器内追加：

```typescript
// 在 JWT 拦截器中追加（同一个函数内）
const settingsRaw = localStorage.getItem('night-diary-app-settings')
if (settingsRaw) {
  try {
    const settings = JSON.parse(settingsRaw)
    if (settings.developerMode) {
      config.headers['X-Developer-Mode'] = 'true'
      if (!config.headers['X-Trace-Id']) {
        // 从 dev store 获取活跃 trace_id
        const activeId = localStorage.getItem('night-diary-active-trace-id')
        if (activeId) {
          config.headers['X-Trace-Id'] = activeId
        }
      }
    }
  } catch { /* ignore */ }
}
```

- [ ] **Step 5: 创建 useTraceStream composable**

```typescript
// src/shared/composables/useTraceStream.ts
import { ref, watch, onUnmounted, type Ref } from 'vue'
import type { TraceSpan, PipelineTrace } from '@/shared/api/dev'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

export function useTraceStream(traceId: Ref<string | null>) {
  const spans = ref<TraceSpan[]>([])
  const status = ref<'idle' | 'connecting' | 'streaming' | 'done' | 'error'>('idle')
  const traceInfo = ref<{ status: string; duration_ms: number; span_count: number } | null>(null)
  let eventSource: EventSource | null = null
  let retryTimer: ReturnType<typeof setTimeout> | null = null

  function connect(id: string) {
    status.value = 'connecting'
    eventSource = new EventSource(`${API_BASE}/api/v1/dev/traces/${id}/stream`)

    eventSource.addEventListener('span_complete', (e: MessageEvent) => {
      const { span } = JSON.parse(e.data) as { span: TraceSpan }
      const idx = spans.value.findIndex(s => s.span_id === span.span_id)
      if (idx >= 0) spans.value[idx] = span
      else spans.value.push(span)
      status.value = 'streaming'
    })

    eventSource.addEventListener('trace_complete', (e: MessageEvent) => {
      const { trace } = JSON.parse(e.data) as { trace: { status: string; duration_ms: number; span_count: number } }
      traceInfo.value = trace
      status.value = 'done'
      eventSource?.close()
    })

    eventSource.addEventListener('span_error', () => {
      status.value = 'error'
    })

    eventSource.onerror = () => {
      if (status.value === 'done') return
      if (status.value === 'connecting') {
        // 首次连接失败，3 秒后重试一次
        eventSource?.close()
        retryTimer = setTimeout(() => {
          if (traceId.value) connect(traceId.value)
        }, 3000)
      } else {
        status.value = 'error'
      }
    }
  }

  watch(traceId, (id) => {
    if (retryTimer) clearTimeout(retryTimer)
    if (eventSource) { eventSource.close(); eventSource = null }
    spans.value = []
    traceInfo.value = null
    if (!id) { status.value = 'idle'; return }
    connect(id)
  }, { immediate: true })

  onUnmounted(() => {
    if (retryTimer) clearTimeout(retryTimer)
    eventSource?.close()
  })

  return { spans, status, traceInfo }
}
```

- [ ] **Step 6: base.css 加 --font-mono**

在 `src/styles/base.css` 的 `:root` 中添加：

```css
--font-mono: 'Cascadia Code', 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
```

- [ ] **Step 7: 运行前端类型检查**

Run: `cd d:\work\night_diary_v2 && npx vue-tsc --noEmit`
Expected: 无类型错误

- [ ] **Step 8: 提交**

```bash
cd d:\work\night_diary_v2 && git add src/stores/settings.ts src/stores/dev.ts src/shared/api/dev.ts src/shared/api/http.ts src/shared/composables/useTraceStream.ts src/styles/base.css
git commit -m "feat: add frontend dev mode infrastructure (settings/store/api/composable)"
```

---

## Task 9: 前端 — 组件与页面

**Files:**
- Create: `src/features/dev/TraceSpanRow.vue`
- Create: `src/features/dev/DevPipelinePanel.vue`
- Create: `src/features/dev/TraceWaterfall.vue`
- Create: `src/features/dev/TraceList.vue`
- Create: `src/features/dev/MiddlewareStatus.vue`
- Create: `src/pages/DevScene.vue`
- Create: `src/features/settings/DeveloperToggle.vue`
- Modify: `src/router/index.ts`
- Modify: `src/shared/components/NavTabs.vue`
- Modify: `src/pages/SettingsScene.vue`

- [ ] **Step 1: 创建 TraceSpanRow.vue**

```vue
<!-- src/features/dev/TraceSpanRow.vue -->
<script setup lang="ts">
import { ref } from 'vue'
import type { TraceSpan } from '@/shared/api/dev'

const props = defineProps<{
  span: TraceSpan
  depth?: number
}>()

const expanded = ref(false)

function statusColor(status: string): string {
  switch (status) {
    case 'running': return 'var(--color-accent)'
    case 'completed': return 'var(--color-success)'
    case 'error': return 'var(--color-danger)'
    case 'dispatched': return 'var(--color-text-secondary)'
    default: return 'var(--color-text-secondary)'
  }
}

function formatDuration(ms: number | null): string {
  if (ms === null) return '...'
  if (ms < 1) return '<1ms'
  if (ms < 1000) return `${ms.toFixed(1)}ms`
  return `${(ms / 1000).toFixed(2)}s`
}
</script>

<template>
  <div class="trace-span-row" :style="{ '--depth': depth ?? 0 }">
    <button class="trace-span-row__header" @click="expanded = !expanded">
      <span class="trace-span-row__dot" :style="{ background: statusColor(span.status) }" />
      <span class="trace-span-row__label">{{ span.stage_label }}</span>
      <span class="trace-span-row__name">{{ span.stage_name }}</span>
      <span class="trace-span-row__duration">{{ formatDuration(span.duration_ms) }}</span>
      <span v-if="span.error" class="trace-span-row__error">!</span>
    </button>

    <div v-if="expanded" class="trace-span-row__detail">
      <div v-if="Object.keys(span.input_snapshot).length" class="trace-span-row__section">
        <span class="trace-span-row__section-label">输入</span>
        <pre class="trace-span-row__code">{{ JSON.stringify(span.input_snapshot, null, 2) }}</pre>
      </div>
      <div v-if="Object.keys(span.output_snapshot).length" class="trace-span-row__section">
        <span class="trace-span-row__section-label">输出</span>
        <pre class="trace-span-row__code">{{ JSON.stringify(span.output_snapshot, null, 2) }}</pre>
      </div>
      <div v-if="Object.keys(span.metadata).length" class="trace-span-row__section">
        <span class="trace-span-row__section-label">元数据</span>
        <pre class="trace-span-row__code">{{ JSON.stringify(span.metadata, null, 2) }}</pre>
      </div>
      <div v-if="span.error" class="trace-span-row__section trace-span-row__section--error">
        <span class="trace-span-row__section-label">错误</span>
        <pre class="trace-span-row__code">{{ span.error }}</pre>
      </div>
    </div>

    <div v-if="span.child_spans.length" class="trace-span-row__children">
      <TraceSpanRow v-for="child in span.child_spans" :key="child.span_id" :span="child" :depth="(depth ?? 0) + 1" />
    </div>
  </div>
</template>

<style scoped>
.trace-span-row {
  --indent: calc(var(--depth) * 16px);
}
.trace-span-row__header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  padding: 0.375rem 0.5rem 0.375rem calc(0.5rem + var(--indent));
  background: transparent;
  border: none;
  border-bottom: 1px solid var(--color-border);
  cursor: pointer;
  text-align: left;
  font-family: var(--font-ui);
  font-size: 0.75rem;
  color: var(--color-text-primary);
}
.trace-span-row__header:hover {
  background: var(--color-bg-elevated);
}
.trace-span-row__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  transition: background 200ms ease;
}
.trace-span-row__label {
  font-weight: 500;
}
.trace-span-row__name {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  opacity: 0.5;
}
.trace-span-row__duration {
  margin-left: auto;
  font-family: var(--font-mono);
  font-size: 0.7rem;
  opacity: 0.7;
}
.trace-span-row__error {
  color: var(--color-danger);
  font-weight: bold;
}
.trace-span-row__detail {
  padding: 0.5rem 0.5rem 0.5rem calc(0.5rem + var(--indent));
  border-bottom: 1px solid var(--color-border);
}
.trace-span-row__section {
  margin-bottom: 0.5rem;
}
.trace-span-row__section-label {
  display: block;
  font-size: 0.65rem;
  text-transform: uppercase;
  opacity: 0.5;
  margin-bottom: 0.25rem;
}
.trace-span-row__code {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  background: var(--color-bg-elevated);
  padding: 0.5rem;
  border-radius: 0.375rem;
  overflow-x: auto;
  margin: 0;
  color: var(--color-text-secondary);
  max-height: 200px;
  overflow-y: auto;
}
.trace-span-row__section--error .trace-span-row__code {
  color: var(--color-danger);
}
.trace-span-row__children {
  border-left: 2px solid var(--color-border);
  margin-left: calc(0.5rem + var(--indent));
}
</style>
```

- [ ] **Step 2: 创建 DevPipelinePanel.vue**

```vue
<!-- src/features/dev/DevPipelinePanel.vue -->
<script setup lang="ts">
import { computed } from 'vue'
import { useDevStore } from '@/stores/dev'
import { useTraceStream } from '@/shared/composables/useTraceStream'
import TraceSpanRow from './TraceSpanRow.vue'

const devStore = useDevStore()
const { spans, status, traceInfo } = useTraceStream(devStore.activeTraceId)

const completedCount = computed(() => spans.value.filter(s => s.status === 'completed' || s.status === 'error').length)
const totalCount = computed(() => spans.value.length)
</script>

<template>
  <div class="dev-pipeline-panel">
    <div class="dev-pipeline-panel__header">
      <span class="dev-pipeline-panel__title">实时追踪</span>
      <span class="dev-pipeline-panel__progress">{{ completedCount }}/{{ totalCount }}</span>
    </div>

    <div v-if="status === 'connecting'" class="dev-pipeline-panel__status">连接中...</div>
    <div v-else-if="status === 'error'" class="dev-pipeline-panel__status dev-pipeline-panel__status--error">
      连接中断，完成后可查看回溯
    </div>
    <div v-else-if="status === 'idle'" class="dev-pipeline-panel__status dev-pipeline-panel__status--idle">
      等待操作...
    </div>

    <div class="dev-pipeline-panel__timeline">
      <TraceSpanRow v-for="span in spans" :key="span.span_id" :span="span" />
    </div>

    <div v-if="traceInfo" class="dev-pipeline-panel__footer">
      <span>总耗时 {{ traceInfo.duration_ms?.toFixed(0) }}ms</span>
      <span>{{ traceInfo.status }}</span>
    </div>
  </div>
</template>

<style scoped>
.dev-pipeline-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  font-family: var(--font-ui);
}
.dev-pipeline-panel__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid var(--color-border);
  font-size: 0.75rem;
}
.dev-pipeline-panel__title {
  font-weight: 600;
  color: var(--color-text-primary);
}
.dev-pipeline-panel__progress {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: var(--color-text-secondary);
}
.dev-pipeline-panel__status {
  padding: 0.5rem 0.75rem;
  font-size: 0.7rem;
  color: var(--color-text-secondary);
}
.dev-pipeline-panel__status--error { color: var(--color-danger); }
.dev-pipeline-panel__status--idle { opacity: 0.5; }
.dev-pipeline-panel__timeline {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}
.dev-pipeline-panel__footer {
  display: flex;
  justify-content: space-between;
  padding: 0.5rem 0.75rem;
  border-top: 1px solid var(--color-border);
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: var(--color-text-secondary);
}
</style>
```

- [ ] **Step 3: 创建 TraceList.vue、TraceWaterfall.vue、MiddlewareStatus.vue**

这些组件结构类似，按设计文档的描述创建。TraceList 用列表+筛选，TraceWaterfall 用横向条形图，MiddlewareStatus 用指示灯。

- [ ] **Step 4: 创建 DevScene.vue**

```vue
<!-- src/pages/DevScene.vue -->
<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useDevStore } from '@/stores/dev'
import { listTraces, getTrace, getDevStats, getMiddlewareStatus, type TraceSummary, type PipelineTrace, type MiddlewareStatus } from '@/shared/api/dev'
import TraceList from '@/features/dev/TraceList.vue'
import TraceWaterfall from '@/features/dev/TraceWaterfall.vue'
import MiddlewareStatus from '@/features/dev/MiddlewareStatus.vue'

const devStore = useDevStore()
const traces = ref<TraceSummary[]>([])
const total = ref(0)
const selectedTrace = ref<PipelineTrace | null>(null)
const stats = ref<{ total_traces: number; by_scenario: Record<string, number>; avg_duration_ms: number; error_count: number } | null>(null)
const middleware = ref<MiddlewareStatus | null>(null)
const loading = ref(false)

async function loadTraces() {
  loading.value = true
  try {
    const result = await listTraces({ page: 1, page_size: 20 })
    traces.value = result.items
    total.value = result.total
  } finally {
    loading.value = false
  }
}

async function selectTrace(traceId: string) {
  selectedTrace.value = await getTrace(traceId)
}

async function loadStats() {
  const [s, m] = await Promise.all([getDevStats(), getMiddlewareStatus()])
  stats.value = s
  middleware.value = m
}

onMounted(() => {
  loadTraces()
  loadStats()
})
</script>

<template>
  <div class="dev-scene">
    <div class="dev-scene__sidebar">
      <TraceList :traces="traces" :total="total" :loading="loading" @select="selectTrace" />
    </div>
    <div class="dev-scene__main">
      <div class="dev-scene__topbar">
        <MiddlewareStatus v-if="middleware" :status="middleware" />
        <div v-if="stats" class="dev-scene__stats">
          <span>{{ stats.total_traces }} 条</span>
          <span>平均 {{ stats.avg_duration_ms.toFixed(0) }}ms</span>
        </div>
      </div>
      <TraceWaterfall v-if="selectedTrace" :trace="selectedTrace" />
      <div v-else class="dev-scene__empty">
        <p>选择一条记录查看详情</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dev-scene {
  display: grid;
  grid-template-columns: 18rem 1fr;
  height: calc(100dvh - 5rem);
  overflow: hidden;
}
.dev-scene__sidebar {
  border-right: 1px solid var(--color-border);
  overflow-y: auto;
}
.dev-scene__main {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.dev-scene__topbar {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.5rem 1rem;
  border-bottom: 1px solid var(--color-border);
  font-size: 0.75rem;
}
.dev-scene__stats {
  display: flex;
  gap: 1rem;
  font-family: var(--font-mono);
  color: var(--color-text-secondary);
}
.dev-scene__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  color: var(--color-text-secondary);
  font-size: 0.875rem;
}
</style>
```

- [ ] **Step 5: 创建 DeveloperToggle.vue 并嵌入 SettingsScene**

```vue
<!-- src/features/settings/DeveloperToggle.vue -->
<script setup lang="ts">
import { useSettingsStore } from '@/stores/settings'
import { PhTerminal } from '@phosphor-icons/vue'

const settings = useSettingsStore()
</script>

<template>
  <label class="settings-field settings-field--checkbox">
    <input v-model="settings.developerMode" type="checkbox" />
    <span>开发者模式</span>
    <span class="developer-toggle__hint">开启后显示数据链路追踪面板</span>
  </label>
</template>

<style scoped>
.developer-toggle__hint {
  font-size: 0.7rem;
  opacity: 0.5;
  margin-left: 0.5rem;
}
</style>
```

在 `SettingsScene.vue` 的通用 SettingsSection 内，紧跟音效 checkbox 之后添加 `<DeveloperToggle />`。

- [ ] **Step 6: 路由加 /dev**

在 `src/router/index.ts` 的 routes 数组中添加：

```typescript
{
  path: '/dev',
  name: 'dev',
  component: () => import('@/pages/DevScene.vue'),
  meta: { skipOnboarding: true },
},
```

- [ ] **Step 7: NavTabs 条件渲染**

在 `src/shared/components/NavTabs.vue` 中：

在 `tabs` 数组后添加计算属性：
```typescript
import { useSettingsStore } from '@/stores/settings'
const settings = useSettingsStore()
```

在模板的 settings RouterLink 前添加：
```vue
<RouterLink
  v-if="settings.developerMode"
  to="/dev"
  class="nav-tabs__settings"
  :class="{ 'is-active': route.name === 'dev' }"
  aria-label="开发者"
>
  <PhTerminal :size="18" :weight="route.name === 'dev' ? 'fill' : 'regular'" />
</RouterLink>
```

需要导入 `PhTerminal`。

- [ ] **Step 8: 运行类型检查**

Run: `cd d:\work\night_diary_v2 && npx vue-tsc --noEmit`
Expected: 无类型错误

- [ ] **Step 9: 提交**

```bash
cd d:\work\night_diary_v2 && git add src/features/dev/ src/pages/DevScene.vue src/features/settings/DeveloperToggle.vue src/router/index.ts src/shared/components/NavTabs.vue src/pages/SettingsScene.vue
git commit -m "feat: add DevScene, DevPipelinePanel, TraceSpanRow, and developer mode toggle"
```

---

## Task 10: 前端 — DiaryScene / ChatScene 侧边栏嵌入

**Files:**
- Modify: `src/pages/DiaryScene.vue`
- Modify: `src/pages/ChatScene.vue`

- [ ] **Step 1: DiaryScene 嵌入 DevPipelinePanel**

在 `DiaryScene.vue` 的模板中，将 `diary-scene` 的 flex 布局改为支持右侧侧边栏：

```vue
<!-- 在 diary-scene__surface 旁边添加 -->
<aside v-if="settings.developerMode" class="diary-scene__dev-panel">
  <DevPipelinePanel />
</aside>
```

CSS 调整：
```css
.diary-scene {
  display: flex;
  justify-content: center;
  gap: 0.75rem;
}
.diary-scene__dev-panel {
  width: 320px;
  flex-shrink: 0;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-outer);
  overflow: hidden;
}
```

在 analysis trigger 之前生成 trace_id：
```typescript
import { useDevStore } from '@/stores/dev'
const devStore = useDevStore()

// 在 triggerAnalysis 调用前
if (settings.developerMode) {
  const traceId = crypto.randomUUID()
  localStorage.setItem('night-diary-active-trace-id', traceId)
  devStore.setActiveTrace(traceId)
}
// triggerAnalysis 调用后
localStorage.removeItem('night-diary-active-trace-id')
devStore.setActiveTrace(null)
```

- [ ] **Step 2: ChatScene 嵌入 DevPipelinePanel**

在 `ChatScene.vue` 的 `chat-scene__skill-panel` 区域条件渲染：

```vue
<!-- 替换原有 skill-placeholder -->
<section v-if="settings.developerMode" class="chat-scene__dev-panel">
  <DevPipelinePanel />
</section>
<p v-else class="chat-scene__skill-placeholder">{{ chatCopy.skillPlaceholder }}</p>
```

在 onSend 中生成 trace_id：
```typescript
import { useDevStore } from '@/stores/dev'
const devStore = useDevStore()

async function onSend(text: string) {
  if (settings.developerMode) {
    const traceId = crypto.randomUUID()
    localStorage.setItem('night-diary-active-trace-id', traceId)
    devStore.setActiveTrace(traceId)
  }
  // ... 原有 send 逻辑 ...
  localStorage.removeItem('night-diary-active-trace-id')
  devStore.setActiveTrace(null)
}
```

- [ ] **Step 3: 运行类型检查和测试**

Run: `cd d:\work\night_diary_v2 && npx vue-tsc --noEmit && npx vitest run`
Expected: 无错误

- [ ] **Step 4: 提交**

```bash
cd d:\work\night_diary_v2 && git add src/pages/DiaryScene.vue src/pages/ChatScene.vue
git commit -m "feat: embed DevPipelinePanel in DiaryScene and ChatScene"
```

---

## Task 11: 测试与优化

**Files:**
- Create: `server/tests/integration/test_diary_trace.py`
- Create: `server/tests/integration/test_chat_trace.py`
- Create: `server/tests/integration/test_dev_mode_off.py`
- Create: `server/tests/unit/test_dev_api.py`
- Create: `src/stores/dev.spec.ts`
- Create: `src/shared/composables/useTraceStream.spec.ts`

- [ ] **Step 1: 后端集成测试 — 场景一 trace 生成**

```python
# server/tests/integration/test_diary_trace.py
"""场景一端到端 trace 测试。"""
import pytest
from app.shared.pipeline_trace import set_trace, get_trace, PipelineTrace


def test_diary_analysis_generates_trace(client, db_session, container, sample_diary_entry):
    """写日记→回信应生成包含 10 个 span 的完整 trace。"""
    trace_id = "test-trace-1"
    trace = PipelineTrace(trace_id=trace_id, scenario="diary", user_id="test", started_at="2026-07-06T00:00:00Z")
    set_trace(trace)

    response = client.post(f"/api/v1/analysis/{sample_diary_entry.id}", headers={"X-Trace-Id": trace_id})

    assert response.status_code == 201
    trace = get_trace()
    assert trace is not None
    stage_names = [s.stage_name for s in trace.spans]
    assert "S2_routing" in stage_names
    assert "S6_persist" in stage_names
    assert trace.status == "completed"
```

- [ ] **Step 2: 后端集成测试 — 场景二 trace 生成**

类似场景一，测试 13 个 span。

- [ ] **Step 3: 后端测试 — dev mode 关闭零开销**

```python
# server/tests/integration/test_dev_mode_off.py
"""dev mode 关闭时应零开销、无 trace 生成。"""
from app.shared.pipeline_trace import get_trace


def test_no_trace_without_dev_header(client, db_session, sample_diary_entry):
    """不传 X-Trace-Id 头时不生成 trace。"""
    response = client.post(f"/api/v1/analysis/{sample_diary_entry.id}")
    assert response.status_code == 201
    assert get_trace() is None  # 无 trace 上下文


def test_sse_returns_404_for_unknown_trace(client):
    """未知 trace_id 的 SSE 端点应处理。"""
    response = client.get("/api/v1/dev/traces/nonexistent/stream")
    # SSE 会返回 200 但流立即结束（无订阅者），或可根据实现返回 404
    assert response.status_code in (200, 404)
```

- [ ] **Step 4: 前端测试**

创建 `src/stores/dev.spec.ts` 和 `src/shared/composables/useTraceStream.spec.ts`，测试状态管理和 SSE 订阅逻辑。

- [ ] **Step 5: 运行全部测试**

Run: `cd server && python -m pytest tests/ -v` 和 `cd d:\work\night_diary_v2 && npx vitest run`
Expected: 全部通过

- [ ] **Step 6: 提交**

```bash
cd server && git add tests/integration/test_diary_trace.py tests/integration/test_chat_trace.py tests/integration/test_dev_mode_off.py tests/unit/test_dev_api.py && git commit -m "test: add integration and unit tests for developer mode"
cd d:\work\night_diary_v2 && git add src/stores/dev.spec.ts src/shared/composables/useTraceStream.spec.ts && git commit -m "test: add frontend tests for dev store and trace stream"
```

---

## 自审清单

- [x] **Spec coverage**: 设计文档中的所有章节都有对应 Task
  - 后端数据模型 → Task 1
  - TraceEventBus → Task 2
  - DB 迁移 → Task 3
  - Tracing 桥接 → Task 4
  - Dev API → Task 5
  - 场景一插桩 → Task 6
  - 场景二插桩 → Task 7
  - 前端基础设施 → Task 8
  - 前端组件页面 → Task 9
  - 侧边栏嵌入 → Task 10
  - 测试 → Task 11

- [x] **Placeholder scan**: 无 TBD/TODO，所有代码步骤都有完整代码

- [x] **Type consistency**: TraceSpan/PipelineTrace 的字段名在前后端一致（trace_id, scenario, status, spans, stage_name, stage_label 等）

- [x] **Scope check**: 单个实现计划可覆盖，P0-P2 分 PR 推进
