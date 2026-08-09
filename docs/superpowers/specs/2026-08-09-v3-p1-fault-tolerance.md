# V3 P1: 多层容错体系

> **阶段**: P1（V3 路线图第二阶段）
> **工期**: 1-1.5 周（经范围调整后从 2 周缩减）
> **前置依赖**: P0（全链路流式输出）已合并到 main（PR #74, commit `8695e8f`）
> **设计来源**: `docs/reports/night-diary-v3-agent-analysis/` dim10 §错误处理与容错（第 1011-1071 行），对标 AgentScope 5 层异常防护

## 1. 目标

补齐 P0 流式链路的异常兜底。P0 实现了"正常路径"的流式输出和基础安全防线，但异常路径（LLM 崩溃、用户中断、任务悬挂）缺少系统性的收口机制。P1 的核心承诺：**无论发生什么异常，前端永不永久卡死，后端资源永不泄漏。**

**成功标准**:
- 流式生成过程中任何异常（LLM 错误、网络断开、CancelledError）都必然发出 `REPLY_END` 事件
- MCP 工具的 session 闭包 bug 修复，工具调用不再因 session 失效而失败
- in_progress background task 在异常退出时自动收口，不悬挂泄漏
- 用户中断流式回复后，后端 10s 内确认终止（可选项，优先级最低）

## 2. 范围

### 范围调整说明（相比初版 spec）

经详细分析后，P1 范围做了以下调整：
- **MCP 完整重连机制** → 简化为 **PersistentMCPConnection**（只修 session 闭包 bug，不做断连重连）。原因：MCP 工具当前在所有环境都未启用（`mcp_endpoints` 默认空），完整重连状态机投入大但无受益方。重连推迟到 P5 或真正启用 MCP 时。
- **abort 端点** → 降级为**可选/低优先级**。原因：P0 的 120s 看门狗已兜底"前端不卡死"，abort 端点解决的是"后端资源释放"和"快速连发竞态"，属于增强而非必须。
- **孤儿进程防护** → 简化为**预留接口**。原因：当前 MCP 走 SSE transport（无子进程），stdio transport 防护推迟到引入子进程式 MCP 时。

### 本阶段包含（核心，必做）
1. **`_terminating_reply` 保证**（层 2）——流式生成器的 try/finally 包裹，异常时必然发出 REPLY_END
2. **TaskRegistry**（层 5）——background task 生命周期管理，替代 P0 的简单 set
3. **PersistentMCPConnection**（层 3）——修复 session 闭包 bug，保持 session 存活

### 本阶段包含（可选，优先级低）
4. **前端 abort 协议**（层 4）——POST /abort + 10s 中断确认超时
5. **孤儿进程防护**——PersistentMCPConnection._cleanup 中预留 process.kill 接口

### 本阶段不包含
- 结构化协议块（P2）
- PlannerAgent（P3）
- 性能探针和 A/B 分流（P5）
- LLM 调用重试机制（报告 dim10 提到的"重试 2 次"——这是 P5 性能优化的范围，P1 只保证"不卡死"，不保证"自动恢复"）
- Redis 取消信号广播（Idealflow 对标项，当前单实例部署不需要，P5 多实例时再引入）

## 3. 架构设计

### 3.1 五层容错体系（对标 AgentScope）

```
┌──────────────────────────────────────────────────────┐
│ 层 5: 任务收口 (TaskFinalizeMiddleware)     ← P1 新增 │
│   异常时 in_progress → failed/done                    │
├──────────────────────────────────────────────────────┤
│ 层 4: 前端看门狗 (useStreamingReply)        ← P1 强化 │
│   120s 无事件回 idle + 10s 中断超时确认               │
├──────────────────────────────────────────────────────┤
│ 层 3: MCP 连接层 (MCPReconnectClient)       ← P1 新增 │
│   ClosedResourceError → 清理 → 重建 → 重连            │
├──────────────────────────────────────────────────────┤
│ 层 2: Agent 层 (_terminating_reply)         ← P1 新增 │
│   异常时必然发出 REPLY_END                            │
├──────────────────────────────────────────────────────┤
│ 层 1: 工具层 (_resilient_call_tool)         ← V2 已有 │
│   异常 → ERROR chunk 回灌模型                         │
└──────────────────────────────────────────────────────┘
```

层 1（工具层）V2 已有：`conversation_loop.py` 的 `_execute_tool` 已有 try/except，异常返回错误字符串回灌模型。P1 不改层 1。

### 3.2 `_terminating_reply` 保证（层 2）

**问题**：P0 的 `generate_reply_streaming` 用 `asyncio.create_task` 启动 background task。如果 task 内部抛出未捕获异常（LLM 崩溃、DB 断开），`publish_reply_end` 永远不会被调用，前端只能靠 120s 看门狗兜底——体验差。

**方案**：在 `conversation_ai_service.py` 的 `generate_reply_streaming` 中用 try/finally 包裹整个流式生成逻辑，确保 `REPLY_END` 必然发出。

```python
async def generate_reply_streaming(...) -> None:
    trace_id = trace_id or ""
    reply_started = False
    try:
        # ... P0 的流式逻辑 ...
        await publish_reply_start(trace_id, intent=...)
        reply_started = True
        # ... 流式推送 TEXT_DELTA ...
        await publish_reply_end(trace_id, citations=..., usage=...)
        reply_end_sent = True
    except asyncio.CancelledError:
        # 用户主动中断——正常收口，不发 error 兜底文本
        if reply_started and not reply_end_sent:
            await publish_reply_end(trace_id, error="cancelled")
        raise  # 传播 CancelledError 给 task 管理器
    except Exception as exc:
        logger.exception("Streaming reply failed: %s", exc)
        if not reply_started:
            await publish_reply_start(trace_id, intent="error")
        await publish_text_delta(trace_id, FALLBACK_FEEDBACK)
        await publish_reply_end(trace_id, error=str(exc))
        reply_end_sent = True
    finally:
        # 最终兜底：except 块若自身异常，这里再补发一次 REPLY_END
        # 不用 asyncio.shield——EventBus.publish 本质是 put_nowait，不会抛异常
        if reply_started and not reply_end_sent:
            with contextlib.suppress(Exception):
                await publish_reply_end(trace_id, error="finalized")
```

**关键设计**：
- `reply_end_sent` 标志位避免正常路径和 except 路径重复发送
- `CancelledError` 单独处理——用户中断不是错误，不发 error 兜底文本
- `finally` 只在 except 路径失败时兜底（`reply_end_sent` 仍为 False 时）
- 不需要 `asyncio.shield`——`TraceEventBus.publish` 的 `put_nowait` 在队列满时只丢弃不抛异常，不会失败

### 3.3 PersistentMCPConnection——修复 session 闭包 bug（层 3）

**问题**：`server/app/services/ai/tool_factory.py` 的 `_load_mcp_tools`（第 264-321 行）有一个确定的 bug：

```python
async with sse_client(endpoint) as (read, write), ClientSession(read, write) as session:
    result = await session.list_tools()
    for mcp_tool in result.tools:
        def make_fn(name):
            async def _call_async(**kwargs):
                resp = await session.call_tool(name, kwargs)  # session 来自闭包
            def _call_sync(**kwargs):
                return asyncio.run(_call_async(**kwargs))
            return _call_sync
        tools[tool_name] = make_fn(tool_name)
# ← async with 退出，session 关闭！
# 后续 _call_sync 调用 session.call_tool → 使用已关闭的 session → 失败
```

**方案**：新增 `PersistentMCPConnection`，将 session 的生命周期从 `async with` 上下文提升到对象实例级别。

```python
# server/app/services/ai/mcp_persistent.py（新增）

class PersistentMCPConnection:
    """MCP 客户端持久连接——保持 session 存活。

    解决 tool_factory.py 中 async with 退出后 session 失效的 bug。
    session 在 connect() 时建立，在 close() 时销毁，中间所有工具
    调用复用同一个 session。

    注意：本版本不做断连重连。如果连接断开，调用会失败并返回
    ERROR chunk 回灌模型（层 1 兜底）。重连机制推迟到 P5 或
    真正启用 MCP 时。
    """

    def __init__(self, endpoint: str):
        self._endpoint = endpoint
        self._session: ClientSession | None = None
        self._cm: Any = None  # sse_client context manager
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        """建立连接并初始化 session。"""
        from mcp import ClientSession
        from mcp.client.sse import sse_client

        self._cm = sse_client(self._endpoint)
        read, write = await self._cm.__aenter__()  # 手动 enter，不退出
        self._session = ClientSession(read, write)
        await self._session.initialize()

    async def list_tools(self) -> Any:
        """列出可用工具（需要已连接）。"""
        if self._session is None:
            raise RuntimeError("Not connected")
        return await self._session.list_tools()

    async def call_tool(self, name: str, args: dict) -> Any:
        """调用工具（需要已连接）。"""
        if self._session is None:
            raise RuntimeError("Not connected")
        return await self._session.call_tool(name, args)

    async def close(self) -> None:
        """关闭连接（应用退出或重载时调用）。"""
        with contextlib.suppress(Exception):
            if self._session:
                await self._session.close()
            self._session = None
        if self._cm:
            with contextlib.suppress(Exception):
                await self._cm.__aexit__(None, None, None)
            self._cm = None
```

**tool_factory.py 改造**：`_load_mcp_tools` 改为返回使用 `PersistentMCPConnection` 的闭包。由于当前项目未实际启用 MCP（`mcp_endpoints` 默认空），改造的风险面很小——只有在配置了 MCP endpoint 时才走新路径。

### 3.4 前端看门狗强化（层 4）

**P0 现状**：`useStreamingReply` 已有 120s 看门狗（无事件强制回 idle）。但缺少：
1. 用户主动中断（点 Stop）后的 10s 确认超时
2. 中断后前端状态与后端的同步

**P1 增强**：

```typescript
// useStreamingReply.ts 扩展

const ABORT_CONFIRM_TIMEOUT_MS = 10_000 // 10s 中断确认超时

function abort(): void {
  if (status.value !== 'streaming') return

  // 发送 abort 信号给后端
  // （通过 fetch abort controller 或专用 POST /messages/abort）

  // 启动 10s 确认定时器
  abortConfirmTimer = setTimeout(() => {
    // 10s 内未收到 REPLY_END → 强制回 idle
    flushTokens()
    status.value = 'idle'
    // 标记为 aborted（区别于正常 done）
  }, ABORT_CONFIRM_TIMEOUT_MS)
}

// 收到 REPLY_END 时清除 abortConfirmTimer
function onReplyEnd() {
  if (abortConfirmTimer) {
    clearTimeout(abortConfirmTimer)
    abortConfirmTimer = null
  }
  // ... P0 逻辑 ...
}
```

**后端中断端点**：新增 `POST /api/v1/conversations/{id}/messages/abort`，接收 trace_id，取消对应的 background task。

### 3.5 任务收口 TaskFinalizeMiddleware（层 5）

**问题**：当前 in_progress 任务（DB 中的 conversation/analysis 状态字段）在异常时无人回写为终态。

**现状分析**：夜记的 conversation 模型当前没有 `status: in_progress` 字段——每次对话是同步的 request-response。但 P0 引入了流式 background task 后，出现了一个隐式的"in_progress"窗口：从 POST `/messages/stream` 返回到 REPLY_END 发出之间。

**P1 方案**：引入轻量级的 `TaskRegistry`，追踪流式 background task 的生命周期。

```python
# server/app/shared/task_registry.py（新增）

class TaskRegistry:
    """流式 background task 生命周期注册表。

    追踪每个 trace_id 对应的 asyncio.Task，确保异常时收口。
    替代 P0 中 conversation.py 的简单 _background_streaming_tasks set。
    """

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def register(self, trace_id: str, task: asyncio.Task[None]) -> None:
        self._tasks[trace_id] = task
        task.add_done_callback(lambda t: self._tasks.pop(trace_id, None))

    async def cancel(self, trace_id: str) -> bool:
        """取消指定 trace_id 的 task。返回是否找到并取消。"""
        task = self._tasks.get(trace_id)
        if task and not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            return True
        return False

    def get_active_trace_ids(self) -> list[str]:
        """返回所有活跃的 trace_id（用于调试/监控）。"""
        return list(self._tasks.keys())

    async def cancel_all(self) -> None:
        """应用关闭时取消所有 task。"""
        for trace_id in list(self._tasks.keys()):
            await self.cancel(trace_id)
```

`conversation.py` 的 `send_message_streaming` 改用 `TaskRegistry`：

```python
task_registry = TaskRegistry()  # 应用级单例

@router.post("/{conversation_id}/messages/stream")
async def send_message_streaming(...):
    # ...
    task = asyncio.create_task(generate_reply_streaming(...))
    task_registry.register(trace_id, task)
    return {"streaming": True, "trace_id": trace_id}
```

### 3.6 孤儿进程防护

**问题**：MCP server 作为子进程（或工具调用派生子进程）时，`CancelledError`（用户中断/超时）触发后子进程未被 kill 而泄漏。

**现状**：夜记的 MCP server 当前作为独立进程运行（通过 `mcp_endpoints` 配置 SSE URL），不是子进程。`MCPReconnectClient` 的重连机制已覆盖连接级别的回收。但如果未来引入子进程式 MCP（stdio transport），需要孤儿防护。

**P1 方案**：在 `MCPReconnectClient._cleanup` 中增加子进程回收逻辑（预留，当前主要走 SSE transport 不触发）。

```python
async def _cleanup(self) -> None:
    # ... 连接清理 ...
    # 如果有子进程（stdio transport），确保 kill
    if hasattr(self, "_process") and self._process:
        with contextlib.suppress(ProcessLookupError):
            self._process.kill()
            await asyncio.wait_for(self._process.communicate(), timeout=3.0)
```

## 4. 数据流

### 4.1 正常流式（P0 已实现，P1 不改）

```
POST /messages/stream → generate_reply_streaming (background task)
  → publish_reply_start
  → publish_text_delta *
  → publish_text_end
  → publish_reply_end
前端 EventSource 接收 → useStreamingReply 渲染
```

### 4.2 异常流式（P1 新增——_terminating_reply 保证）

```
POST /messages/stream → generate_reply_streaming (background task)
  → publish_reply_start
  → publish_text_delta *...
  → 💥 LLM 崩溃 / DB 断开 / 网络错误
  → except Exception:
      → publish_text_delta(FALLBACK_FEEDBACK)  # 错误兜底文本
      → publish_reply_end(error=str(exc))      # 带错误标记的终止
      → reply_end_sent = True
  → finally:（仅当 except 块自身也失败时才兜底）
      → if not reply_end_sent: publish_reply_end(error="finalized")

前端: 收到 REPLY_END(error) → status='done' → 显示兜底文本
```

### 4.3 用户中断（P1 可选——abort 协议，优先级低）

```
前端: 用户点 Stop
  → POST /messages/abort {trace_id}
  → useStreamingReply.abort() → 启动 10s 确认定时器

后端:
  → task_registry.cancel(trace_id)
  → generate_reply_streaming 收到 CancelledError
  → except CancelledError:
      → publish_reply_end(error="cancelled")
  → task 结束

前端: 收到 REPLY_END → 清除 10s 定时器 → status='done'
  （如果 10s 内没收到 REPLY_END → 强制回 idle）
```

### 4.4 MCP 工具调用（P1 修复 session bug）

```
工具调用 → PersistentMCPConnection.call_tool(name, args)
  → session 存活（P1 修复）→ 正常返回结果
  → 如果 session 断连 → 调用失败 → 返回 ERROR chunk 回灌模型（层 1 兜底）
  → 不自动重连（推迟到 P5）
```

## 5. 错误处理矩阵

| 场景 | P0 行为 | P1 改进 |
|------|---------|---------|
| 流式中 LLM 崩溃 | 无处理，task 静默死亡，前端靠 120s 看门狗 | `_terminating_reply`：发兜底文本 + REPLY_END(error) |
| 流式中 DB 断开 | 同上 | 同上 |
| 用户点 Stop | 无后端 abort，前端靠 120s 看门狗 | 10s 中断确认 + 后端 task cancel |
| MCP 连接断开 | 后续工具调用全部失败 | 自动重连（3 次退避） |
| background task 泄漏 | `_background_streaming_tasks` set 无生命周期管理 | `TaskRegistry` + done_callback 自动清理 |
| 应用关闭时 task 未收口 | task 随进程退出被强制 kill | `cancel_all()` 优雅收口 |

## 6. 测试策略

### 6.1 后端单元测试

| 测试文件 | 覆盖范围 |
|---------|---------|
| `tests/unit/services/test_conversation_ai_service.py`（扩展） | `_terminating_reply`：模拟 LLM 异常，验证 REPLY_END 必然发出；CancelledError 路径不发兜底文本 |
| `tests/unit/services/ai/test_mcp_persistent.py`（新增） | PersistentMCPConnection：connect 后 session 存活、close 后 session 释放、tool 闭包引用持久 session |
| `tests/unit/shared/test_task_registry.py`（新增） | TaskRegistry：注册、取消、done_callback 自动清理、cancel_all |

### 6.2 前端测试（可选，依赖 abort 端点实现）

| 测试文件 | 覆盖范围 |
|---------|---------|
| `useStreamingReply.spec.ts`（扩展） | abort() 启动 10s 定时器、REPLY_END 清除定时器、10s 超时强制 idle |

### 6.3 集成测试

| 测试文件 | 覆盖范围 |
|---------|---------|
| `tests/e2e/test_streaming_resilience.py`（新增） | 端到端：LLM 崩溃后前端收到 REPLY_END（error 标记）；可选：abort 端点取消 task |

### 6.4 Eval 闸门

P1 合并前必须通过现有 eval 基线（与 P0 相同），确保容错改造不引入生成质量退化。

## 7. 实施顺序（按依赖关系）

### 核心路径（必做，约 1 周）
1. **TaskRegistry**（最基础，其他都依赖它进行 task 管理）
2. **`_terminating_reply` 保证**（依赖 TaskRegistry 的 cancel 能力来测试 CancelledError 路径）
3. **PersistentMCPConnection + tool_factory 改造**（最独立，可与 1-2 并行）

### 可选路径（优先级低，约 0.5 周，有余力时做）
4. **abort 端点 + 前端 10s 确认定时器**（依赖 TaskRegistry）
5. **孤儿进程防护**（在 PersistentMCPConnection.close 中预留接口）

## 8. 验证清单

### 核心交付（必做）
- [ ] `generate_reply_streaming` 的 try/finally 包裹 + `reply_end_sent` 标志（_terminating_reply 保证）
- [ ] `TaskRegistry` 实现 + `conversation.py` 集成（替代简单 set）
- [ ] `PersistentMCPConnection` 实现（修复 session 闭包 bug）
- [ ] `tool_factory.py` 改用 PersistentMCPConnection
- [ ] 所有单元测试通过
- [ ] 现有 eval 基线不退化

### 可选交付（低优先级）
- [ ] `POST /messages/abort` 端点
- [ ] 前端 `useStreamingReply.abort()` + 10s 确认定时器
- [ ] 孤儿进程防护（PersistentMCPConnection.close 中的 process.kill 预留）
