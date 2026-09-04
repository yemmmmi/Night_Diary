# PR12 Spec：MCP 工具注册表（ToolRegistry）与开发者可观测性

- **日期**: 2026-09-04
- **状态**: 待审阅
- **方向**: MCP consumer 做实（方向 B）
- **前置决策**: 方案二（独立 ToolRegistry 服务）；trace 嵌入（B 级观测）+ 持久化

## 1. 背景与问题

夜记 agent 的工具系统目前是"内置写死"：

- `tool_factory.py` 产出 8 个本地工具（search_diary、get_weather_info、analyze_sentiment、query_entity_graph、list_todos、get_plan_progress、get_plan_detail、get_user_address），每次 agent 调用时现建 tool_map
- `mcp_persistent.py` + `MCP_ENDPOINTS` 配置的 MCP 消费能力只是骨架：best-effort 加载、无健康检查、无文档、从未做实
- 联网搜索能力藏在 plan_skill 内部（Tavily→DuckDuckGo 降级链），agent 工具面上没有

问题：
1. 外部工具（天气、联网搜索、网页抓取）与代码耦合，接入新工具必须改代码发版
2. 开发者（项目唯一用户）完全看不见 agent 用了哪些工具、调用了什么、进程状态如何——黑盒
3. MCP 骨架从未被使用，属于半死代码

## 2. 目标

1. **统一工具入口**：新建 `ToolRegistry`，本地工具与 MCP 远程工具注册进同一个注册表，agent loop 只认注册表
2. **可插拔外部工具**：通过 `MCP_ENDPOINTS`（SSE/HTTP）与 `MCP_STDIOS`（stdio 子进程）配置接入任意 MCP server，无需改代码
3. **开发者透明度**：
   - Dev 面板新增「MCP」标签页（端点健康、工具清单、调用流水）
   - MCP 调用作为 `S8_mcp` span 嵌入 pipeline trace，前端链路视图可查
   - 调用记录持久化到 `mcp_call_logs` 表
4. **多用户进程观察**：共享进程模型 + per-user 调用记录，进程指标（pid/重启次数）在面板与 trace 中可见，用于理解多用户场景下进程对 agent 的影响

## 3. 非目标

- 不做 MCP provider（不对外暴露夜记能力，那是另一个方向）
- 不做 MCP 工具市场/UI 配置界面（单人自用，env 配置文件足够）
- 不做每用户独立 MCP 进程（有状态工具出现前不需要，架构已留口）
- 不做实时事件流（SSE 推送面板刷新，nice-to-have，成本高收益小）
- 不迁移 plan_skill 内置的 web_search——本次只做 MCP 通道，plan_skill 保持现状
- 本地工具不产生 S8_mcp span（S6_skills 已覆盖，避免噪音）

## 4. 架构设计

### 4.1 组件与数据流

```
配置层                 统一工具注册表 (新)                    消费方
┌─────────────┐      ┌──────────────────────────┐      ┌────────────────┐
│ MCP_ENDPOINTS│     │  ToolRegistry            │      │ agent loop      │
│ (env, SSE)   │────▶│  ├─ local tools (8个)     │─────▶│  (conversation_ │
├─────────────┤      │  │   tool_factory 产出     │      │   ai_service)   │
│ MCP_STDIOS   │     │  ├─ mcp tools (N个)       │      └────────────────┘
│ (env, 子进程) │────▶│  │   McpConnection 抽象:   │      ┌────────────────┐
├─────────────┤      │  │   · SseMcpConnection   │      │ Dev API         │
│ 内置工具      │     │  │   · StdioMcpConnection │────▶│  /dev/mcp/*     │
│ (tool_factory)│────▶│  ├─ call(): 分发+span埋点  │      │  (面板新标签页)  │
└─────────────┘      │  │   + mcp_call_logs 落库 │      └────────────────┘
                     │  └─ 命名空间/健康/退避重启  │      ┌────────────────┐
                     └──────────────────────────┘      │ pipeline trace  │
                              trace_span("S8_mcp")─────▶  (已有 trace 视图)│
                                                        └────────────────┘
```

### 4.2 ToolRegistry

位置：`server/app/services/ai/tool_registry.py`（与 tool_factory 同层）

- `initialize(container, user_id)`：
  - 从 tool_factory 拿本地 8 工具注册
  - 解析 `MCP_ENDPOINTS`：每条 `{alias}:{url}`，建 `SseMcpConnection`
  - 解析 `MCP_STDIOS`：每条 `{alias}:{command} {args} [key=value...]`，建 `StdioMcpConnection`
  - 连接成功后 `list_tools`，工具以 `mcp__{alias}__{原始工具名}` 注册
  - 条目级失败隔离：单个端点失败只标记 unhealthy，不阻塞启动
- `call(name, arguments)`：统一分发。本地工具直调；MCP 工具走对应连接，包 `trace_span("S8_mcp")` + 写 `mcp_call_logs`（best-effort，失败记日志不阻塞）
- `close()`：关停所有连接（stdio：terminate → 5s 等待 → kill）
- 生命周期：挂进 `ServiceContainer`（与 episodic memory 同级），`ensure_ai_stack` 时初始化

### 4.3 连接层双形态（McpConnection 抽象）

**SseMcpConnection**：HTTP/SSE 端点，无进程管理，复用 `mcp_persistent.py` 的连接逻辑。

**StdioMcpConnection**：子进程管理（核心复杂度所在）

| 关注点 | 设计 |
|---|---|
| 启动 | spawn `command + args + env`；Windows 下 `npx`/`uvx` 用 `shutil.which` 解析全路径或 `shell=True`；Docker 内直 exec |
| 健康 | 进程存活检查 + 每次 call 前校验；死亡 → 指数退避重启（1s→2s→4s，上限 3 次），仍失败标记 dead，工具从 agent 可用集摘除 |
| 并发 | stdio 单管道：每连接一把 `asyncio.Lock` 串行化调用 |
| 超时 | 默认 30s，超时杀进程重启 |
| 关停 | ServiceContainer 关闭时 terminate 进程树 → 5s 等待 → kill，无孤儿进程 |

**多用户显式取舍**：共享进程模型（每端点 1 个全局进程，靠调用层传 user_id）+ 每调用记录 user_id 落库。面板把"当前进程数/重启次数/正在被谁调用"做成可见指标。将来有状态工具可按 user_id 分叉连接，`McpConnection` 抽象已留口。

### 4.4 agent loop 集成（平滑迁移）

- agent loop（conversation_ai_service）从"每次现建 tool_map"改为"向 registry 要"
- registry 对外暴露与现状同构的 `dict[str, ToolFn]` + ToolSpec 列表，LangChain bind_tools 链路零改动
- 工具对 LLM 完全透明：只是工具列表变长了，前端/信件流零适配
- 危机检测/安全防线在 skill 路由之前，不受影响

## 5. 配置与命名空间

### 5.1 配置格式

```bash
# server/.env（新增）
MCP_ENDPOINTS="search:http://localhost:9201/sse,weather:http://localhost:9202/sse"
MCP_STDIOS="tavily:uvx tavily-mcp api_key=xxx,fetch:npx -y @modelcontextprotocol/server-fetch"
```

- 端点别名由用户定义，作命名空间与面板展示名
- 条目级失败隔离：坏行（URL 错/命令不存在/进程起不来）只标记该端点 unhealthy，日志给出明确原因
- stdio 的 env 键值（API key 等）注入子进程环境变量，**永不进参数快照与日志**

```yaml
# docker-compose.yml（新增可选 profile "mcp"）
services:
  mcp-tavily:   # uvx 打包的搜索 MCP server 容器
    profiles: [mcp]
  mcp-fetch:    # fetch server
    profiles: [mcp]
```

### 5.2 工具命名空间

- 格式：`mcp__{端点别名}__{原始工具名}`，如 `mcp__tavily__search`
- 撞名拒绝：与本地工具或另一 MCP 工具全名撞名时，启动拒绝重复注册并记 warning，后注册者跳过（保持工具集确定性）
- 本地工具名不变（8 个），agent 可用工具集 = 本地 8 + N 个 MCP 工具
- LLM 侧零感知：tool spec 原样透传

### 5.3 默认行为（零回归约束）

`MCP_ENDPOINTS`/`MCP_STDIOS` 均为空时，registry 只含本地 8 工具，行为与当前完全一致。本 PR 对现有功能零影响，纯增量。

## 6. 数据模型与观测

### 6.1 `mcp_call_logs` 表（新建，与 llm_call_logs 平行）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | int PK | 自增 |
| user_id | str | 多租户隔离 |
| trace_id / span_id | str | 关联 pipeline trace，支持双向跳转 |
| endpoint_alias | str | `tavily` / `search` |
| transport | str | `sse` / `stdio` |
| tool_name | str | `mcp__tavily__search` |
| raw_tool_name | str | `search` |
| status | str | `success` / `error` / `timeout` |
| duration_ms | int | 耗时 |
| error_message | str null | 失败原因 |
| arguments_snapshot | JSON | 截断 2KB |
| result_snapshot | JSON | 截断 2KB |
| created_at | datetime | 调用时间 |

写入 best-effort：失败记日志不阻塞调用。API key 不进快照。

### 6.2 Dev API（挂现有 dev 路由，只读，与 traces 一致无鉴权）

- `GET /dev/mcp/status`：端点健康清单（alias、transport、健康态、工具数、重启次数、pid、last_error、加载时间）
- `GET /dev/mcp/tools`：全量工具清单（namespaced 名、来源徽标 local/端点别名、描述）
- `GET /dev/mcp/calls`：调用流水（分页 + endpoint/status/user 过滤）

### 6.3 Dev 面板「MCP」标签页（前端）

- **端点卡片区**：绿/灰健康点、transport 徽标、stdio 进程指标（pid、重启次数）——进程死亡/退避重启可见
- **工具清单表**：来源徽标区分本地 8 工具与 MCP 远程工具，"agent 当前能用什么"的唯一事实源
- **调用流水列表**：时间/用户/工具/耗时/状态，点开看参数与结果快照，trace_id 可跳回该封信的链路图
- 视觉沿用纸白/墨色/细线/8px 圆角设计体系，不引入新样式概念

### 6.4 trace 嵌入（S8_mcp span）

- 每次 MCP 工具调用产生一个 `S8_mcp` span，嵌在 S5 Agent 父 span 下，与 S6_skills、S7b_rag 同级
- metadata：`transport`、`restart_count`、`pid`、`endpoint_alias`、`raw_tool_name`
- 前端链路视图（已有 TraceDetail 组件）直接渲染：节点行显示工具全名+耗时条+状态点；点开展开 input/output 快照、进程指标徽标、失败原因原文、跳转链接
- 超时/失败红色呈现（如"pid 4301→4308、重启 1 次·已恢复"）
- 本地工具不产生 span

## 7. 测试策略

### 7.1 后端单测（主力）

- 配置解析：多端点/多行、坏行隔离、stdio env 键值解析
- 命名空间：`mcp__alias__tool` 生成、撞名拒绝、本地工具名不受影响
- stdio 进程管理：spawn 失败→unhealthy 不阻塞启动、崩溃→退避重启（mock 时序 1s→2s→4s）、超时杀进程、close 无孤儿
- 调用分发：本地/MCP 路由正确、超时/异常状态落库、快照截断 2KB、日志写失败不影响调用（best-effort 断言）
- stdio 测试用内联 Python 脚本当假 MCP server（stdin/stdout JSON-RPC mock），不依赖外部命令——Windows/Docker/CI 全平台可跑

### 7.2 后端 e2e

起本地假 SSE MCP server，agent 消息带工具调用 → 断言 S8_mcp span 落 trace、mcp_call_logs 有记录、/dev/mcp/* 三端点返回正确。

### 7.3 前端 vitest

MCP 标签页渲染（端点卡/工具表/调用流水）、健康态徽标、stdio 指标展示、加载失败降级空态。

### 7.4 手动验收（Docker 全栈）

1. `--profile mcp` 拉起 tavily + fetch，面板端点全绿、工具清单出现 `mcp__tavily__search`
2. 笔谈问「今天上海天气怎么样」→ agent 走工具 → 信流回复带真实结果
3. `docker kill mcp-tavily` → 面板端点变灰、工具摘除、信件降级回复不受影响；重启容器 → 自动恢复
4. trace 视图：链路图有 S8_mcp span，点开见 transport/pid/重启次数
5. MySQL 查 mcp_call_logs：user_id/耗时/状态齐全

## 8. 验收标准（DoD）

- 配置为空时全量测试通过且行为与今天一致（零回归）
- 配置 MCP 后：面板可见、trace 可查、调用流水落库、进程故障可恢复可观察
- pytest / ruff / mypy / vitest / vue-tsc / eslint / CI 全绿
- 无 Co-Authored-By；PR 描述按模板（标题/功能描述/实现思路/测试方式）

## 9. 工作量与 PR 划分

| 项 | 预估 |
|---|---|
| 后端 registry + 连接层 | ~2 天 |
| Dev API + mcp_call_logs 表 | ~0.5 天 |
| 前端 MCP 标签页 | ~1 天 |
| 测试 | ~1.5 天 |
| **合计** | **~5 个工作日，单 PR** |

改动集中在 `server/app/services/ai/` + dev 路由 + `src/web/` 面板，无跨模块侵入。

## 10. 风险与对策

| 概率 | 风险 | 对策 |
|---|---|---|
| 中 | Windows 上 stdio 子进程管理坑（npx 解析、进程树终止） | shutil.which 全路径解析；job object/taskkill 进程树终止；内联脚本测试覆盖两平台路径 |
| 中 | agent loop 迁移到 registry 引入回归 | 默认配置=纯本地 8 工具零变化；迁移 PR 单独提交可回滚；全量 pytest 保证 |
| 低 | MCP server 返回的 tool schema 与 OpenAI function calling 不兼容 | tool spec 校验层：不合法 schema 的工具拒绝注册记 warning，不进 agent 工具集 |
| 低 | mcp_call_logs 膨胀 | 快照截断 2KB；后续可加保留期清理（与 backup 保留 20 份同思路），本次不做 |

## 11. Open Questions（待用户拍板，不阻塞 spec）

无——四个澄清问题（方向/边界/观测深度/持久化）均已在对话中拍板。
