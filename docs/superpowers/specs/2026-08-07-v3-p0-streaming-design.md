# V3 P0: 全链路流式输出与流式安全

> **阶段**: P0（V3 路线图第一阶段）
> **工期**: 2-3 周
> **前置依赖**: 清理分支合并到 main
> **设计来源**: `docs/reports/night-diary-v3-agent-analysis/` 第二版 §4.2.1, §4.2.4

## 1. 目标

将场景二（多轮对话）和场景一（日记→AI 回信）的 AI 回复从"完整生成后一次性返回"升级为 **token 级流式输出**，同时确保危机安全网不被流式绕过。

**成功标准**:
- 场景二：低风险意图走 token 级流式，首 token 逼近 LLM 生成延迟（目标 < 1s，正式基线由 P5 探针实测确认）
- 场景一：Empathy 分段 → Insight 分段的流式输出
- 危机意图：流式完全降级为非流式，沿用 V2 现有安全路径
- 前端永不永久卡死（120s 看门狗 + 10s 中断超时）
- 保留非流式回退路径，灰度发布

## 2. 范围

### 本阶段包含
- `LLMClient` Protocol 新增 `astream` 方法
- SSE 流式事件类型设计（8 种）
- 流式安全策略（三道防线）
- 场景二 `ConversationLoop` 流式改造（先行）
- 场景一 `Supervisor.synthesize` 流式改造（跟进）
- 前端 `useStreamingReply` composable + RAF 批量更新 + 看门狗
- 流式安全策略的单元测试
- 非流式回退路径保留

### 本阶段不包含
- 结构化协议块（P2）
- 多层容错体系中的 MCP 重连 / 孤儿进程防护（P1）
- 中间件管道（P7 可选）
- PlannerAgent（P3）
- 性能探针和 A/B 分流（P5）

## 3. 架构设计

### 3.1 流式事件类型

在现有 `TraceEventBus`（`server/app/shared/trace_event_bus.py`）之上扩展，新增 8 种流式内容事件。TraceEventBus 已有基于 `trace_id` 的 pub/sub 机制和 asyncio.Queue 满负载丢弃策略，直接复用。

| 事件类型 | 方向 | 载荷 | 说明 |
|----------|------|------|------|
| `REPLY_START` | 后端→前端 | `{trace_id, intent, reply_id}` | 标记一次回复开始，前端进入 streaming 状态 |
| `TEXT_DELTA` | 后端→前端 | `{text: string}` | 增量文本片段（token 或批量） |
| `TEXT_END` | 后端→前端 | `{}` | 当前文本块结束 |
| `REPLY_END` | 后端→前端 | `{trace_id, citations?, usage?}` | 回复完全结束，前端回到 idle |
| `RETRACT` | 后端→前端 | `{reason: string, replacement: string}` | 安全回撤：前端整段替换为安全模板 |
| `PROTOCOL_BLOCK` | 后端→前端 | `{type, data}` | 结构化协议块（P2 预留，P0 仅定义不消费） |
| `STATE_UPDATED` | 后端→前端 | `{key, value}` | 状态变更通知（P1 预留） |
| `TRACE_SPAN` | 后端→前端 | `{span}` | 现有追踪 span 事件（兼容保留） |

事件通过现有 SSE 端点 `/api/v1/dev/traces/{trace_id}/stream` 传输，前端通过 `EventSource.addEventListener` 按事件名路由。

### 3.2 LLMClient Protocol 扩展

`server/app/shared/llm.py` 的 `LLMClient` Protocol 新增 `astream`：

```python
class LLMClient(Protocol):
    def invoke(self, prompt: str) -> Any: ...
    async def ainvoke(self, prompt: str) -> Any: ...
    async def astream(self, prompt: str) -> AsyncGenerator[str, None]: ...
```

`astream` 返回 `AsyncGenerator[str, None]`，逐 token yield 纯文本。具体实现由 `TracingLLMClient`（`server/app/shared/tracing_llm.py`）委托给底层 LangChain 模型的 `.astream()` 方法。

`ToolCapableLLMClient` 同步扩展 `astream`。流式 + 工具调用的交互逻辑：**工具调用轮次保持非流式**（`ainvoke`），仅最终回复轮次走 `astream`。这避免了流式中途中断执行工具的复杂度。

### 3.3 流式安全策略（三道防线）

解决"token 级流式 vs 后置危机检测"的冲突。核心问题：如果危机内容已经逐 token 流到前端，再检测就来不及了。

**按意图分级，复用现有 `CrisisGuard`（`server/app/shared/crisis_guard.py`）**：

| 防线 | 机制 | 适用范围 | 实现位置 |
|------|------|---------|---------|
| **1. 危机意图非流式** | `ChatIntentClassifier` 命中 `crisis_signal` 或 `CrisisGuard.detect(user_input)` 返回 True → 整体降级为非流式（完整生成→双重检测→安全模板短路） | crisis_signal 意图（强制） | `ConversationLoop` 入口 |
| **2. 首段缓冲放行** | 流式回复首 N 字符（80-120）先在后端缓冲，通过快速规则检测（复用 `CrisisGuard` 关键词，零 LLM 成本）后才开始向前端放行，之后转为 token 级直通 | emotional_vent / advice_seeking | 新增 `StreamingSafetyGuard` |
| **3. 滑动窗口审核** | 流式过程中后端持续对最近窗口（120 字符）做规则检测，命中时立即发 `RETRACT` 事件 + 替换为安全模板 | 全部流式路径（兜底） | 新增 `StreamingSafetyGuard` |

低风险意图（`casual_chat` / `retrospective_query`）走纯 token 级直通，不付缓冲代价。

**新增组件：`StreamingSafetyGuard`**（`server/app/shared/streaming_safety.py`）

```python
class StreamingSafetyGuard:
    """流式安全守卫——三道防线按意图分级。"""

    def __init__(self, crisis_guard: CrisisGuard, buffer_size: int = 100, window_size: int = 120):
        self._crisis = crisis_guard
        self._buffer_size = buffer_size
        self._window_size = window_size

    def should_stream_directly(self, intent: str, user_input: str) -> bool:
        """防线 1：判断是否可以走纯流式（True=可以，False=必须非流式）。"""
        if intent == "crisis_signal":
            return False
        return not self._crisis.detect(user_input)

    async def filter_stream(
        self, token_stream: AsyncGenerator[str, None], intent: str
    ) -> AsyncGenerator[str | dict, None]:
        """防线 2+3：包装 token 流，先缓冲后放行，滑动窗口审核。"""
        # 低风险意图直接透传
        if intent in ("casual_chat", "retrospective_query"):
            async for token in token_stream:
                yield token
            return

        # 情感敏感意图：首段缓冲 + 滑动窗口
        buffer = ""
        buffered_tokens: list[str] = []
        flushed = False

        async for token in token_stream:
            buffered_tokens.append(token)
            if not flushed:
                buffer += token
                if len(buffer) >= self._buffer_size:
                    if self._crisis.detect(buffer):
                        yield {"retract": True, "replacement": self._crisis.safe_response}
                        return
                    flushed = True
                    yield buffer  # 一次性放行缓冲
            else:
                # 滑动窗口审核
                window = (buffer + token)[-self._window_size:]
                buffer = buffer[len(buffer) - (self._window_size - len(token)):]
                if self._crisis.detect(window):
                    yield {"retract": True, "replacement": self._crisis.safe_response}
                    return
                yield token

        # 缓冲未满（短回复），最后检查一次
        if not flushed and buffer:
            if self._crisis.detect(buffer):
                yield {"retract": True, "replacement": self._crisis.safe_response}
                return
            yield buffer
```

### 3.4 场景二流式改造（先行）

`server/app/services/ai/conversation_loop.py` 的 `ConversationLoop`：

**改造点**：第 5 阶段（Output）的最终回复生成改为流式。

```
现有流程:
  Stage 4 Agentic Loop → 最终回复(ainvoke) → 返回完整文本 → API 一次性响应

P0 流式流程:
  Stage 4 Agentic Loop → 意图安全判定(防线1) → 最终回复(astream) → 安全守卫过滤(防线2+3) → SSE 逐 token 推送
  ↓ 危机意图                                        ↓ 低风险意图
  非流式回退(ainvoke + 安全模板短路)           直接 token 级透传
```

**API 层改造**：`server/app/api/v1/conversation.py`

现有 POST `/api/v1/conversation/{diary_id}/chat` 返回 JSON。P0 新增流式路径：

- 方案：POST 仍返回 `{trace_id, reply_id}`，前端通过 SSE 端点 `/api/v1/dev/traces/{trace_id}/stream` 接收流式内容事件
- 与现有 `TraceEventBus` 集成：流式 token 通过 `bus.publish(trace_id, {"type": "TEXT_DELTA", "text": token})` 推送
- 前端收到 `REPLY_END` 后，再通过 REST 获取 `citations` 和 `usage`（载荷较大，不放 SSE）

**非流式回退**：`ConversationLoop` 保留 `generate_reply()` 同步方法，当流式不可用（LLM 不支持 astream）或危机意图时回退。

### 3.5 场景一流式改造（跟进）

`server/app/domain/agents/supervisor.py` 的 `SupervisorAgent.synthesize()`：

改为 async generator，分两段 yield：
1. Empathy 段先流出（共情回复）
2. Insight 段后流出（洞察分析）

场景一同样通过 `TraceEventBus` 推送 `TEXT_DELTA` 事件。

### 3.6 前端流式架构

**新增 composable：`src/shared/composables/useStreamingReply.ts`**

```typescript
export function useStreamingReply() {
  const replyText = ref('')
  const status = ref<'idle' | 'streaming' | 'done' | 'retracted'>('idle')

  // RAF 批量更新
  let pendingTokens = ''
  let rafId: number | null = null

  function flushTokens() {
    replyText.value += pendingTokens
    pendingTokens = ''
    rafId = null
  }

  function onTextDelta(text: string) {
    pendingTokens += text
    if (rafId === null) {
      rafId = requestAnimationFrame(flushTokens)
    }
  }

  // 看门狗：120s 无事件强制回 idle
  let watchdogTimer: ReturnType<typeof setTimeout> | null = null
  function resetWatchdog() { /* ... */ }

  // RETRACT 处理：整段替换
  function onRetract(replacement: string) {
    replyText.value = replacement
    status.value = 'retracted'
  }

  // ... 连接/断开/清理逻辑
  return { replyText, status, onTextDelta, onRetract }
}
```

**关键设计**：
- **RAF 批量更新**：`TEXT_DELTA` 事件不直接写 `ref`，而是累积到 `pendingTokens`，在 `requestAnimationFrame` 回调中一次性 flush，避免高频事件导致渲染卡顿
- **120s 看门狗**：每收到任意事件重置定时器，120s 内无事件强制回 idle 状态
- **10s 中断超时**：用户点 Stop 后启动 10s 定时器，超时未收到 `REPLY_END` 则强制回 idle
- **RETRACT 处理**：收到 `RETRACT` 事件时整段替换 `replyText`，不追加

**前端文件改动清单**：
- 新增：`src/shared/composables/useStreamingReply.ts`
- 修改：`src/stores/chat.ts`（集成流式状态）
- 修改：`src/features/chat/ChatMessage.vue`（渲染流式文本）
- 修改：`src/features/chat/OutputPanel.vue`（流式输出区域）

## 4. 数据流

### 4.1 场景二流式数据流

```
用户消息
  → POST /api/v1/conversation/{diary_id}/chat
  → ConversationLoop.run()
    → Stage 1-3: SessionContext + 预处理 + 意图分类
    → StreamingSafetyGuard.should_stream_directly(intent, user_input)
      → False (危机) → 非流式: ainvoke → 安全模板 → 返回 JSON
      → True → 继续
    → Stage 4: Agentic Loop (工具调用轮次, ainvoke, 非流式)
    → Stage 5: 最终回复
      → LLM.astream(prompt) → AsyncGenerator[str]
      → StreamingSafetyGuard.filter_stream(token_stream, intent)
        → 缓冲/滑窗过滤
        → TraceEventBus.publish(trace_id, {type: "TEXT_DELTA", text: token})
      → 生成结束
      → TraceEventBus.publish(trace_id, {type: "REPLY_END", citations, usage})
  ← POST 返回 {trace_id, reply_id}

前端:
  → EventSource(/api/v1/dev/traces/{trace_id}/stream)
  → useStreamingReply 接收事件
    → TEXT_DELTA → RAF 批量更新
    → RETRACT → 整段替换
    → REPLY_END → 停止看门狗，获取完整 citations
```

### 4.2 场景一流式数据流

```
用户提交日记
  → POST /api/v1/analysis/trigger
  → ExecutionPlanner → MultiAgentGraph.invoke()
    → Phase 0: RetrievalAgent
    → Phase 1: EmpathyAgent ∥ InsightAgent (各自 astream)
    → Supervisor.synthesize() → async generator
      → yield Empathy 段 → TraceEventBus TEXT_DELTA
      → yield Insight 段 → TraceEventBus TEXT_DELTA
    → REPLY_END
  ← POST 返回 {trace_id}
```

## 5. 错误处理

| 场景 | 处理 |
|------|------|
| LLM 不支持 `astream` | 回退到 `ainvoke`，非流式返回 |
| 流式中途连接断开 | 前端看门狗 120s 超时 → 回 idle，保留已收到的部分文本 |
| 流式中途 LLM 错误 | 后端发 `REPLY_END`（带 error 标记）+ 错误兜底文本，保证前端不卡死 |
| 流式中途检测到危机 | 发 `RETRACT` + 安全模板替换 |
| 用户主动中断 | 前端发 abort 信号，后端 10s 内确认 → `REPLY_END` |

**P0 不包含**：MCP 自动重连、孤儿进程防护、任务收口——这些是 P1 容错体系的范围。

## 6. 测试策略

### 6.1 后端单元测试

| 测试文件 | 覆盖范围 |
|---------|---------|
| `tests/unit/shared/test_streaming_safety.py`（新增） | 三道防线：危机非流式、首段缓冲放行、滑窗审核触发 RETRACT |
| `tests/unit/shared/test_llm.py`（扩展） | `astream` Protocol 合规性、`TracingLLMClient` 流式委托 |
| `tests/unit/services/ai/test_conversation_loop.py`（扩展） | 流式路径切换、危机降级、工具轮次非流式 |
| `tests/unit/shared/test_trace_event_bus.py`（扩展） | 流式事件 publish/subscribe 正确性 |

### 6.2 前端测试

| 测试文件 | 覆盖范围 |
|---------|---------|
| `src/shared/composables/__tests__/useStreamingReply.spec.ts`（新增） | RAF 批量更新、看门狗超时、RETRACT 替换 |

### 6.3 Eval 闸门

P0 合并前必须通过现有 eval 基线（`make eval-rag` 容差 0.05 + `make eval-generation`），确保流式改造不引入生成质量退化。

## 7. 迁移策略

1. **保留非流式回退**：`ConversationLoop.generate_reply()` 同步方法保留，流式是增量路径
2. **灰度发布**：通过环境变量 `STREAMING_ENABLED=true/false` 控制是否启用流式，默认 false，测试通过后切换
3. **场景二先行**：场景二的改造风险更低（已有 SSE 基础设施），验证通过后再改场景一

## 8. 验证清单

- [ ] `LLMClient.astream` Protocol 定义 + `TracingLLMClient` 实现
- [ ] `StreamingSafetyGuard` 三道防线实现 + 单元测试
- [ ] `ConversationLoop` 流式路径（含危机降级）
- [ ] 场景一 `Supervisor.synthesize` 流式改造
- [ ] SSE 事件类型扩展（8 种）
- [ ] 前端 `useStreamingReply` composable（RAF + 看门狗 + RETRACT）
- [ ] 前端 `ChatMessage.vue` / `OutputPanel.vue` 流式渲染
- [ ] 现有 eval 基线不退化（`make eval-rag` + `make eval-generation`）
- [ ] 非流式回退路径可用（`STREAMING_ENABLED=false`）
