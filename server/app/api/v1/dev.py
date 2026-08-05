"""用于管道追踪检查的开发者模式 API 路由。

提供列出、查看、删除和实时流式传输管道追踪的端点，
以及聚合统计和中间件健康检查。这些路由面向开发者/调试用途，
不需要认证。
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, func

from app.api.deps import DbDep
from app.infrastructure.models.pipeline_trace import PipelineTraceRow
from app.shared.pipeline_trace import get_trace
from app.shared.trace_event_bus import get_event_bus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dev", tags=["dev"])

# SSE 心跳间隔（秒）。若在该时间窗口内没有事件到达，
# 则发送一个心跳注释以保持连接存活。
_SSE_HEARTBEAT_INTERVAL = 30.0


def _format_sse(event: dict[str, Any]) -> str:
    """将 dict 格式化为 SSE 消息字符串。

    使用 ``default=str``，使不可 JSON 序列化的值（datetime 等）
    被转为字符串，而不是抛出异常。
    """
    event_type = event.get("type", "message")
    data = json.dumps(event, ensure_ascii=False, default=str)
    return f"event: {event_type}\ndata: {data}\n\n"


# ── 中间件可用性辅助函数 ──────────────────────────────────────


def _check_redis() -> bool:
    """若 Redis 客户端已连接则返回 ``True``。"""
    try:
        from app.infrastructure.redis_client import is_redis_available

        return is_redis_available()
    except Exception:
        return False


def _check_neo4j() -> bool:
    """若 Neo4j 驱动已连接则返回 ``True``。"""
    try:
        from app.infrastructure.entity_graph import is_neo4j_available

        return is_neo4j_available()
    except Exception:
        return False


def _check_langgraph() -> bool:
    """若 LangGraph 可导入则返回 ``True``。"""
    try:
        from app.services.ai.conversation_graph import LANGGRAPH_AVAILABLE

        return bool(LANGGRAPH_AVAILABLE)
    except Exception:
        return False


def _check_rq() -> bool:
    """若 RQ 任务队列已初始化则返回 ``True``。

    RQ 的可用性由 ``app.infrastructure.task_queue`` 中的
    ``_redis_queue`` 单例推断 —— 当 Redis 不可用或未安装
    ``rq`` 包时，该单例保持 ``None``，任务回退到守护线程执行。
    """
    try:
        from app.infrastructure.task_queue import _redis_queue

        return _redis_queue is not None
    except Exception:
        return False


# ── 追踪列表 ───────────────────────────────────────────────────────────


def _row_to_summary(row: PipelineTraceRow) -> dict[str, Any]:
    """将 ``PipelineTraceRow`` 转换为摘要 dict（不含 ``trace_json``）。"""
    return {
        "trace_id": row.trace_id,
        "scenario": row.scenario,
        "user_id": row.user_id,
        "status": row.status,
        "started_at": row.started_at,
        "ended_at": row.ended_at,
        "duration_ms": row.duration_ms,
        "span_count": row.span_count,
        "ref_id": row.ref_id,
    }


@router.get("/traces")
def list_traces(
    db: DbDep,
    scenario: str | None = Query(None, description="Filter by scenario"),
    status_filter: str | None = Query(
        None, alias="status", description="Filter by status"
    ),
    ref_id: str | None = Query(None, description="Filter by ref_id"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
) -> dict[str, Any]:
    """列出管道追踪，支持可选过滤与分页。"""
    query = db.query(PipelineTraceRow)

    if scenario:
        query = query.filter(PipelineTraceRow.scenario == scenario)
    if status_filter:
        query = query.filter(PipelineTraceRow.status == status_filter)
    if ref_id:
        query = query.filter(PipelineTraceRow.ref_id == ref_id)

    total = query.count()

    offset = (page - 1) * page_size
    rows = (
        query.order_by(desc(PipelineTraceRow.created_at))
        .offset(offset)
        .limit(page_size)
        .all()
    )
    items = [_row_to_summary(r) for r in rows]
    return {"items": items, "total": total}


# ── 追踪详情 ─────────────────────────────────────────────────────────


@router.get("/traces/{trace_id}")
def get_trace_detail(trace_id: str, db: DbDep) -> dict[str, Any]:
    """返回单条追踪的完整 JSON 负载。"""
    row = db.get(PipelineTraceRow, trace_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")
    if row.trace_json:
        try:
            data: dict[str, Any] = json.loads(row.trace_json)
            return data
        except (json.JSONDecodeError, TypeError):
            # 若 JSON 损坏则回退到摘要。
            return _row_to_summary(row)
    return _row_to_summary(row)


# ── 追踪删除 ─────────────────────────────────────────────────────────


@router.delete(
    "/traces/{trace_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_trace(trace_id: str, db: DbDep) -> Response:
    """按 ID 删除管道追踪。"""
    row = db.get(PipelineTraceRow, trace_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── SSE 流 ───────────────────────────────────────────────────────────


@router.get("/traces/{trace_id}/stream")
async def stream_trace(
    trace_id: str, request: Request, db: DbDep
) -> StreamingResponse:
    """实时追踪的 Server-Sent Events 流。

    首先推送所有已完成的 span（来自内存中的活跃追踪或持久化的数据库行），
    然后订阅 ``TraceEventBus`` 获取实时事件，直到追踪完成或客户端断开连接。

    每隔 30 秒空闲发送一次心跳，以防止代理超时。
    """
    # 在会话有效时从数据库收集初始状态。
    initial_events: list[dict[str, Any]] = []
    trace_already_complete = False

    # 1. 内存中的活跃追踪（同一上下文 —— 涵盖 SSE 消费者与生产者
    #    共享 contextvar 的罕见情况）。
    active_trace = get_trace()
    if active_trace is not None and active_trace.trace_id == trace_id:
        for span in active_trace.spans:
            initial_events.append(
                {
                    "type": "span",
                    "trace_id": trace_id,
                    "span": span.to_dict(),
                }
            )
        if active_trace.status in ("completed", "error"):
            initial_events.append(
                {
                    "type": "trace_complete",
                    "trace_id": trace_id,
                    "trace": active_trace.to_dict(),
                }
            )
            trace_already_complete = True

    # 2. 持久化的数据库行 —— 为进行中的追踪推送已完成的 span，
    #    若追踪已结束则推送完整负载。
    if not trace_already_complete:
        row = db.get(PipelineTraceRow, trace_id)
        if row is not None and row.trace_json:
            try:
                persisted = json.loads(row.trace_json)
                if row.status in ("completed", "error"):
                    initial_events.append(
                        {
                            "type": "trace_complete",
                            "trace_id": trace_id,
                            "trace": persisted,
                        }
                    )
                    trace_already_complete = True
                else:
                    for span in persisted.get("spans", []):
                        initial_events.append(
                            {
                                "type": "span",
                                "trace_id": trace_id,
                                "span": span,
                            }
                        )
            except (json.JSONDecodeError, TypeError):
                pass

    return StreamingResponse(
        _trace_event_generator(
            trace_id, request, initial_events, trace_already_complete
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _trace_event_generator(
    trace_id: str,
    request: Request,
    initial_events: list[dict[str, Any]],
    trace_already_complete: bool,
) -> AsyncGenerator[str, None]:
    """生成 SSE 格式追踪事件的异步生成器。

    1. 产出所有 ``initial_events``（已完成的 span）。
    2. 若追踪尚未完成，则订阅 ``TraceEventBus`` 并流式传输实时事件。
    3. 空闲 30 秒后发送心跳。
    4. 在 ``trace_complete`` 事件或客户端断开后关闭。
    """
    # 1. 推送已完成的 span。
    for event in initial_events:
        yield _format_sse(event)

    # 若追踪已结束，立即关闭流。
    if trace_already_complete:
        return

    # 2. 订阅 EventBus 以获取实时事件。
    bus = get_event_bus()
    queue = await bus.subscribe(trace_id)
    try:
        while True:
            # 等待前检查客户端是否已断开。
            if await request.is_disconnected():
                break

            try:
                event = await asyncio.wait_for(
                    queue.get(),
                    timeout=_SSE_HEARTBEAT_INTERVAL,
                )
            except TimeoutError:
                # 发送心跳以保持连接存活。
                yield _format_sse(
                    {"type": "heartbeat", "trace_id": trace_id}
                )
                continue

            yield _format_sse(event)

            # 追踪结束后关闭流。
            if event.get("type") == "trace_complete":
                break
    finally:
        await bus.unsubscribe(trace_id, queue)


# ── 统计 ────────────────────────────────────────────────────────────────


@router.get("/stats")
def get_dev_stats(db: DbDep) -> dict[str, Any]:
    """跨所有管道追踪的聚合统计。"""
    total_traces = db.query(PipelineTraceRow).count()

    # 按场景分组。
    scenario_rows = (
        db.query(PipelineTraceRow.scenario, func.count(PipelineTraceRow.trace_id))
        .group_by(PipelineTraceRow.scenario)
        .all()
    )
    by_scenario = {scenario: count for scenario, count in scenario_rows}

    # 平均时长（不含 duration_ms 的行会被 AVG 忽略）。
    avg_duration = db.query(func.avg(PipelineTraceRow.duration_ms)).scalar()
    avg_duration_ms = float(avg_duration) if avg_duration is not None else 0.0

    # 错误数。
    error_count = (
        db.query(PipelineTraceRow)
        .filter(PipelineTraceRow.status == "error")
        .count()
    )

    return {
        "total_traces": total_traces,
        "by_scenario": by_scenario,
        "avg_duration_ms": avg_duration_ms,
        "error_count": error_count,
    }


# ── 中间件状态 ────────────────────────────────────────────────────────────


@router.get("/middleware-status")
def get_middleware_status() -> dict[str, Any]:
    """基础设施中间件的健康检查。"""
    return {
        "redis": _check_redis(),
        "neo4j": _check_neo4j(),
        "langgraph": _check_langgraph(),
        "rq": _check_rq(),
    }
