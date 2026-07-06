# 开发者模式 — Agent 数据链路可视化

> 设计日期：2026-07-06
> 状态：待审核
> 关联文档：`.trae/agent-data-flow/agent-data-flow.html`（两大场景完整数据链路报告）

## 1. 目标

为夜记 V2 新增「开发者模式」，开启后可清晰看见用户输入在 Agent 数据链路中经过的每一层变化，最终如何形成输出。覆盖两个会话场景：

- **场景一：写日记 → 回信**（asyncio 并发，MultiAgentGraph 三阶段）
- **场景二：会话 → 多轮对话**（LangGraph StateGraph 6 节点 / Legacy Loop 降级）

两种查看方式：
- **实时追踪**：写日记/发消息时，侧边栏逐个亮起数据流经的管道阶段
- **回溯查看**：DevScene 独立页查看任意历史 trace 的完整链路详情

## 2. 链路覆盖范围

### 场景一 TraceSpan 映射（10 个主阶段）

| 阶段 | stage_name | 对应代码 | 记录内容 |
|------|------------|---------|---------|
| S1 归一化 | `S1_normalize` | `ContentNormalizer.from_diary/from_card` | 输入文本 → UnifiedMemoryAtom |
| S2 路由决策 | `S2_routing` | `ExecutionPlanner.plan` | tier + mode 选择 |
| S3 分类 | `S3_classify` | `SupervisorAgent.classify` | intent/crisis/skills/routing/budget（5 个子 span） |
| S4a 检索 | `S4a_retrieval` | `retrieval_agent.run` | episodic_context + compressed_history → retrieval_context |
| S4b 共情 | `S4b_empathy` | `empathy_agent.run` | 写信核心输出 |
| S4c 洞察 | `S4c_insight` | `insight_agent.run` | 洞察生成输出 |
| S5 合成 | `S5_synthesize` | `SupervisorAgent.synthesize` | LLM 合并或直取 → final_response |
| S6 持久化 | `S6_persist` | `_persist_analysis` | 写 analyses 表 |
| S7-S9 记忆同步 | `S7_memory` | `_sync_diary_to_memory` | 归一化 → 四维检查 → 情景+长期写入（3 个子 span） |
| S10 实体提取 | `S10_entity` | `schedule_entity_extraction` | 标记 dispatched 状态 |

### 场景二 TraceSpan 映射（13 个主阶段）

| 阶段 | stage_name | 对应代码 | 记录内容 |
|------|------------|---------|---------|
| S1 会话路由 | `S1_session` | `SessionContext` | L1 内存 + L2 Redis |
| S2 危机检测 | `S2_crisis` | `CrisisGuard.detect` | 命中则短路，跳过 S3-S8 |
| S3 输入预处理 | `S3_preprocess` | `InputPreprocessor.process` | 5 个子 span：清洗/NFC/安全/省略补全/否定 |
| S4 意图分类 | `S4_intent` | `ChatIntentClassifier.classify_sync` | 规则层 + LLM 层 → 6 类意图 |
| S5 槽位抽取 | `S5_slot` | `SlotExtractor.extract` | 时间/情绪/操作/多任务/风格约束 |
| S6 技能选择 | `S6_skills` | `SkillRegistry.select_skills` | 4 技能激活状态 |
| S7a 查询改写 | `S7a_query_rewrite` | `QueryUnderstander.understand` | 指代消解 + 声明式改写 |
| S7b RAG 检索 | `S7b_rag` | `_retrieve_related_diary_ids` | 向量检索 → diary_ids |
| S7c 情景记忆 | `S7c_episodic` | `_format_episodic_memories` | 三源：日记 → 夜话 → 情绪卡片 |
| S7d 工具构建 | `S7d_tools` | `_build_tools` | intent 过滤子集 + MCP 动态接入 |
| S8 Agentic Loop | `S8_loop` | LangGraph 6 节点 / Legacy Loop | 6 个子 span：preprocess/understand/plan/execute_tools/generate/postprocess |
| S9 输出 | `S9_output` | Citation 标注 | 参考来源汇总 |
| S10-S13 记忆回写 | `S10_memory` | `_maybe_persist_episodic` 等 | 情景记忆写入/风格反馈/实体提取/会话更新（4 个子 span） |

每个 TraceSpan 统一记录：`stage_name` / `stage_label` / `status` / `duration_ms` / `input_snapshot` / `output_snapshot` / `metadata` / `child_spans[]` / `error`。

## 3. 后端数据模型

### 3.1 核心数据结构

```python
@dataclass
class TraceSpan:
    span_id: str                    # uuid4
    stage_name: str                 # "S3_preprocess"
    stage_label: str                # "输入预处理"
    status: str                     # "running" | "completed" | "error" | "dispatched"
    started_at: float               # time.perf_counter()
    ended_at: float | None
    duration_ms: float | None
    input_snapshot: dict[str, Any]  # 截断后的快照
    output_snapshot: dict[str, Any]
    metadata: dict[str, Any]
    child_spans: list["TraceSpan"]
    error: str | None

@dataclass
class PipelineTrace:
    trace_id: str                   # 前端生成，通过 X-Trace-Id 传入
    scenario: str                   # "diary" | "chat"
    user_id: str
    started_at: str                 # ISO timestamp
    status: str                     # "running" | "completed" | "error"
    spans: list[TraceSpan]
    _span_stack: list[TraceSpan]   # 嵌套栈，支持 parent/child

    def start_span(self, name, label, **input_snapshot) -> TraceSpan
    def end_span(self, status="completed", **output_snapshot) -> None
    def end(self, status="completed") -> None
    def to_dict(self) -> dict
```

### 3.2 ContextVar 传播

```python
_current_trace: ContextVar[PipelineTrace | None] = ContextVar("pipeline_trace", default=None)

def get_trace() -> PipelineTrace | None:
    return _current_trace.get()
```

用 `ContextVar` 在 async 调用链中隐式传播，无需修改任何函数签名。`asyncio.gather` 和 `asyncio.create_task` 会复制当前 ContextVar 值到子任务。RQ daemon thread 不在 async 上下文中，`get_trace()` 返回 None，实体提取等异步旁路任务在主流程 span 中标记 `dispatched` 状态，不追踪旁路内部细节。

### 3.3 trace_span 上下文管理器

```python
@contextmanager
def trace_span(stage_name: str, stage_label: str, **input_snapshot):
    trace = get_trace()
    if trace is None:
        yield None                # dev mode 关闭，直接跳过
        return
    span = trace.start_span(stage_name, stage_label, truncate(input_snapshot))
    try:
        yield span
    except Exception as e:
        trace.end_span(status="error", error=str(e))
        raise
    else:
        trace.end_span(status="completed")
```

使用方式：

```python
def preprocess_node(state: ConversationState) -> dict:
    with trace_span("S8.1_preprocess", "预处理节点", raw_text=state["content"]) as span:
        result = InputPreprocessor().process(state["content"])
        if span:
            span.metadata["safety_flag"] = result.safety_flag
        return {"clean_text": result.text, "preprocess_result": result}
```

### 3.4 快照截断策略

| 数据类型 | 截断规则 |
|---------|---------|
| `str` | 截断 500 字符，尾部加 `...` |
| `dict` | 最多 20 个 key，每个 value 递归截断 |
| `list` | 记录总数 + 前 3 个元素 |
| `bytes`/二进制 | 仅记录类型名和长度 |
| 其他 | `str(obj)[:500]` |

### 3.5 持久化

```sql
CREATE TABLE pipeline_traces (
    trace_id     TEXT PRIMARY KEY,
    scenario     TEXT NOT NULL,          -- 'diary' | 'chat'
    user_id      TEXT NOT NULL,
    status       TEXT NOT NULL,          -- 'completed' | 'error'
    started_at   TEXT NOT NULL,          -- ISO timestamp
    ended_at     TEXT,
    duration_ms  REAL,
    span_count   INTEGER,
    ref_id       TEXT,                   -- diary_id 或 conversation_id
    trace_json   TEXT NOT NULL,          -- 完整 trace 序列化 JSON
    created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_traces_user ON pipeline_traces(user_id, started_at DESC);
CREATE INDEX idx_traces_scenario ON pipeline_traces(scenario, started_at DESC);
```

### 3.6 开发者模式开关 — 请求头驱动

前端 Axios 拦截器在 `settings.developerMode === true` 时附加：
- `X-Developer-Mode: true`
- `X-Trace-Id: {crypto.randomUUID()}`

后端 FastAPI 依赖注入读取请求头决定是否创建 trace。关闭时 `get_trace()` 返回 None → `trace_span()` yield None → 所有 `if span:` 分支跳过。实测仅增加微秒级 ContextVar 查询。

### 3.7 现有 Tracing 桥接

不替换现有体系，通过 `trace_id` 关联：

| 现有表 | 改动 | 关联方式 |
|--------|------|---------|
| `llm_call_logs` | 新增 `trace_id TEXT` 列 | `TracingLLMClient.ainvoke()` 从 ContextVar 读 trace_id |
| `agent_decisions` | 新增 `trace_id TEXT` 列 | `SupervisorAgent.classify()` 写入时附带 |
| `skill_activations` | 新增 `trace_id TEXT` 列 | `SkillActivationTracer` 从 ContextVar 读 |

## 4. SSE 实时推送

### 4.1 TraceEventBus

```python
class TraceEventBus:
    """内存事件总线，trace span 完成时推送事件给 SSE 订阅者"""
    _subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
    _lock = asyncio.Lock()

    async def subscribe(self, trace_id: str) -> asyncio.Queue
    async def unsubscribe(self, trace_id: str, queue: asyncio.Queue)
    async def publish(self, trace_id: str, event: dict)  # QueueFull 时丢弃，不阻塞管道
```

### 4.2 SSE 端点

```python
@router.get("/api/v1/dev/traces/{trace_id}/stream")
async def stream_trace(trace_id: str, request: Request):
    async def event_generator():
        queue = await event_bus.subscribe(trace_id)
        try:
            # 先推送已完成的 spans（防止订阅晚于管道启动）
            trace = get_trace()
            if trace:
                for span in trace.spans:
                    yield format_sse({"type": "span_complete", "span": span.to_dict()})
            # 持续监听新事件
            while True:
                if await request.is_disconnected():
                    break
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield format_sse(event)
                if event.get("type") == "trace_complete":
                    break
        finally:
            await event_bus.unsubscribe(trace_id, queue)
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

### 4.3 推送时机

只在 span 完成时推送一次 `span_complete`，包含完整 input/output/duration。不推送 `span_start`，减少网络流量。

### 4.4 SSE 事件格式

```json
{"type": "span_complete", "trace_id": "abc", "span": {"span_id": "...", "stage_name": "S3_preprocess", "stage_label": "输入预处理", "status": "completed", "duration_ms": 12.3, "input_snapshot": {...}, "output_snapshot": {...}, "metadata": {...}, "child_spans": [...]}}

{"type": "trace_complete", "trace_id": "abc", "trace": {"status": "completed", "duration_ms": 3450, "span_count": 13}}

{"type": "span_error", "trace_id": "abc", "span": {...}, "error": "ConnectionError: ..."}

{"type": "heartbeat"}
```

### 4.5 边界情况

| 情况 | 处理方式 |
|------|---------|
| SSE 连接晚于管道启动 | 端点先推送已完成 spans，再监听新事件 |
| 前端关闭页面断开 | `request.is_disconnected()` 检测，自动 unsubscribe |
| 管道异常中断 | `trace_span` 的 except 分支推送 `span_error` + `trace_complete(status=error)` |
| 慢消费者 | `QueueFull` 时丢弃事件，不阻塞管道 |
| EventBus 内存泄漏 | trace 完成后 30s 清理订阅队列；兜底 TTL 5 分钟 |
| dev mode 关闭（无活跃 trace） | SSE 端点返回 404（trace_id 不在 EventBus 中） |

## 5. API 设计

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/v1/dev/traces/{trace_id}/stream` | SSE 实时订阅 |
| GET | `/api/v1/dev/traces` | 历史 trace 列表（参数：scenario, page, page_size, status, ref_id） |
| GET | `/api/v1/dev/traces/{trace_id}` | 单条 trace 详情 |
| DELETE | `/api/v1/dev/traces/{trace_id}` | 删除一条 trace |
| GET | `/api/v1/dev/stats` | 统计数据（total_traces, by_scenario, avg_duration 等） |
| GET | `/api/v1/dev/middleware-status` | 中间件健康状态（redis, neo4j, mysql, langgraph 等） |

## 6. 前端设计

### 6.1 新增文件清单

| 路径 | 类型 | 职责 |
|------|------|------|
| `src/stores/settings.ts` | 修改 | 新增 `developerMode` 字段 |
| `src/stores/dev.ts` | 新建 | 开发者模式状态管理 |
| `src/shared/api/dev.ts` | 新建 | Dev API 服务层 |
| `src/shared/api/http.ts` | 修改 | 拦截器附加 dev 头 |
| `src/shared/composables/useTraceStream.ts` | 新建 | SSE 订阅 composable |
| `src/features/dev/DevPipelinePanel.vue` | 新建 | 侧边栏实时追踪面板 |
| `src/features/dev/TraceSpanRow.vue` | 新建 | 单个 span 行（可展开） |
| `src/features/dev/TraceWaterfall.vue` | 新建 | 瀑布图组件（回溯详情用） |
| `src/features/dev/MiddlewareStatus.vue` | 新建 | 中间件健康状态 |
| `src/features/dev/TraceList.vue` | 新建 | 历史 trace 列表 |
| `src/pages/DevScene.vue` | 新建 | 开发者模式独立页 |
| `src/router/index.ts` | 修改 | 新增 `/dev` 路由 |
| `src/shared/components/NavTabs.vue` | 修改 | 条件渲染开发者 Tab |
| `src/pages/DiaryScene.vue` | 修改 | 嵌入 DevPipelinePanel |
| `src/pages/ChatScene.vue` | 修改 | 嵌入 DevPipelinePanel |
| `src/features/settings/DeveloperToggle.vue` | 新建 | 设置页开关 |

### 6.2 设计原则

遵循 frontend-design 和 frontend-skill 原则：

- **去卡片化**：DevScene 用工作区布局（左侧列表 + 主工作区），不用 dashboard-card mosaic。Span 展示用列表行 + 分割线，不用独立卡片容器
- **色彩克制**：不引入新色系，仅复用项目现有令牌（`--color-accent` 运行中、`--color-success` 完成、`--color-danger` 错误）
- **实用文案**：标题操作导向（"追踪记录"而非"历史 Trace 列表"、"服务状态"而非"中间件状态 + 统计"）
- **动效克制**：仅保留 3 处（span 完成圆点亮起、详情滑入展开、侧边栏滑入）
- **字体**：UI 文本用 `--font-ui`，数据/快照用 `--font-mono`（新增 `'Cascadia Code', 'JetBrains Mono', monospace`）

### 6.3 实时追踪侧边栏 — DevPipelinePanel

垂直时间线布局：
- 左侧竖线 + 圆点节点（颜色编码状态：琥珀=运行中、绿=完成、红=错误）
- 右侧文字内容（阶段名 + 耗时）
- 点击行展开详情面板（底部滑出，不推挤其他元素）
- 顶部进度条：已完成 span 数 / 总 span 数
- 底部总耗时和状态

宽度 320px，可折叠收起。嵌入 DiaryScene 编辑器右侧、ChatScene 对话区右侧（复用现有 `chat-scene__skill-panel` 区域）。

### 6.4 DevScene 独立页 — `/dev`

Linear 风格工作区布局：

- **左侧窄边栏**：追踪记录列表（trace_id / 场景 / 状态 / 时间 / 耗时），筛选和分页
- **主工作区**：选中 trace 的瀑布图详情，或管道流程静态总览（未选中时）
- **顶部状态条**：服务状态指示灯（Redis/Neo4j/MySQL/LangGraph/RQ 内联）+ 用量统计

### 6.5 SSE 订阅 composable — useTraceStream

```typescript
export function useTraceStream(traceId: Ref<string | null>) {
  const spans = ref<TraceSpan[]>([])
  const status = ref<'idle' | 'connecting' | 'streaming' | 'done' | 'error'>('idle')
  // EventSource 监听 span_complete / trace_complete / span_error
  // 断开重试一次，仍失败显示"实时追踪不可用，完成后可查看回溯"
  onUnmounted(() => eventSource?.close())
  return { spans, status }
}
```

### 6.6 trace_id 协调

前端发起请求前生成 `trace_id`（`crypto.randomUUID()`），通过一个模块级 `Ref<string | null>` 共享给侧边栏和 Axios 拦截器：

1. DiaryScene/ChatScene 发起请求前：`activeTraceId.value = crypto.randomUUID()`
2. Axios 拦截器检测到 `activeTraceId.value` 非空时附加 `X-Trace-Id` 头
3. DevPipelinePanel 通过 `useTraceStream(activeTraceId)` 建立 SSE 连接
4. 请求完成后（成功或失败）：`activeTraceId.value = null`，SSE 自动关闭

POST 请求和 SSE 连接共用同一个 trace_id。若 `activeTraceId` 为 null，拦截器不附加头，后端不创建 trace。

### 6.7 NavTabs 条件渲染

开发者 Tab 仅在 `settings.developerMode === true` 时显示，用 `v-if` 控制一个带终端图标的 RouterLink。

### 6.8 AnalysisScene 集成

回信详情页已有 `AIAnalysisPanel.vue` 展示 token 详情。开发者模式下额外渲染"查看完整链路"按钮，点击跳转到 DevScene 的 trace 详情视图。

## 7. 错误处理

### 7.1 核心原则

开发者模式本身不能影响主业务流程。任何 trace 相关的异常都必须被吞掉并记录，绝不能向上传播。

### 7.2 后端错误处理

| 场景 | 处理方式 |
|------|---------|
| `trace_span` 内业务异常 | 业务异常正常 raise，span 记录 `status=error` 后 re-raise |
| `PipelineTrace` 序列化失败 | `logger.warning`，跳过持久化 |
| SSE 客户端断开 | `is_disconnected()` 检测，自动清理 |
| EventBus `QueueFull` | 丢弃事件，不阻塞管道 |
| trace_json 过大（>1MB） | 截断 child_spans 快照，保留 stage_name 和 duration |
| pipeline_traces 写入失败 | `logger.warning`，best-effort |

### 7.3 前端错误处理

| 场景 | 处理方式 |
|------|---------|
| EventSource 连接失败 | 3 秒后重试一次，仍失败显示回溯提示 |
| EventSource 中断 | 保留已收到 spans，显示"连接中断" |
| Dev API 404 | dev mode 被后端关闭，隐藏侧边栏 |
| 快照过大渲染卡顿 | 虚拟滚动 + 默认折叠 |

### 7.4 零开销保证

dev mode 关闭时完整路径：请求进入 → 无 `X-Developer-Mode` 头 → `get_dev_trace()` 返回 None → `_current_trace` 未设置 → `get_trace()` 返回 None → `trace_span()` yield None → `if span:` 跳过。每次 `trace_span` 调用仅一次 ContextVar.get() + 一次 None 检查，约 0.1 微秒级。

## 8. 测试策略

### 8.1 后端测试（pytest）

| 测试文件 | 测试内容 | 约用例数 |
|---------|---------|---------|
| `tests/unit/test_pipeline_trace.py` | 数据结构、序列化、嵌套、截断 | 12 |
| `tests/unit/test_trace_span.py` | 上下文管理器：正常/异常/dev关闭/嵌套 | 8 |
| `tests/unit/test_trace_event_bus.py` | subscribe/publish/QueueFull/清理 | 6 |
| `tests/unit/test_dev_api.py` | API 端点：列表/详情/删除/SSE/404/鉴权 | 10 |
| `tests/integration/test_diary_trace.py` | 场景一端到端：10 个 span 正确生成 | 4 |
| `tests/integration/test_chat_trace.py` | 场景二端到端：13 个 span 正确生成 | 4 |
| `tests/integration/test_dev_mode_off.py` | dev 关闭：零开销、无 trace、SSE 404 | 3 |

### 8.2 前端测试（vitest）

| 测试文件 | 测试内容 |
|---------|---------|
| `stores/dev.spec.ts` | 状态管理逻辑 |
| `composables/useTraceStream.spec.ts` | SSE 订阅/断开/重连/事件解析 |
| `api/dev.spec.ts` | API 函数调用和返回类型 |
| `features/dev/DevPipelinePanel.spec.ts` | 组件渲染和交互 |

### 8.3 性能验证

| 指标 | 目标 |
|------|------|
| dev 关闭时每次 trace_span 开销 | < 1 微秒 |
| dev 开启时管道总开销增加 | < 5% |
| trace_json 平均大小 | < 100KB |
| SSE 事件延迟 | < 50ms |
| DevScene trace 列表加载 | < 200ms |

## 9. 实施路径

建议按以下顺序分 PR 推进：

1. **P0 — 后端基础设施**：PipelineTrace/TraceSpan 数据结构、ContextVar、trace_span 上下文管理器、TraceEventBus、pipeline_traces 表 + Alembic 迁移
2. **P0 — 后端插桩**：场景一 10 个 span 插桩、场景二 13 个 span 插桩、现有 tracing 表 trace_id 桥接
3. **P0 — 后端 API**：Dev API 路由（列表/详情/SSE/删除/统计/中间件状态）
4. **P1 — 前端基础设施**：settings.developerMode 字段、dev store、dev API 服务、http 拦截器改动、useTraceStream composable
5. **P1 — 前端组件**：DevPipelinePanel、TraceSpanRow、TraceWaterfall、TraceList、MiddlewareStatus、DeveloperToggle
6. **P1 — 前端页面**：DevScene、路由、NavTabs 条件渲染、DiaryScene/ChatScene 侧边栏嵌入、AnalysisScene 集成
7. **P2 — 测试与优化**：全部单元/集成测试、性能验证、快照截断调优
