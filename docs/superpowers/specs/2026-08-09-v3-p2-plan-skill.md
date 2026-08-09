# V3 P2: 协议块基础设施 + 计划 Skill

> **阶段**: P2（V3 路线图第二阶段——重构后）
> **工期**: 2-3 周
> **前置依赖**: P0（流式输出）+ P1（容错体系）已合并到 main（commit `c5e4557`）
> **设计来源**:
> - `docs/reports/night-diary-v3-agent-analysis/` §P.1-P.2.5（双轮驱动定位 + 任务规划域设计）
> - `docs/reports/night-diary-v3-agent-analysis/` dim6/dim8（协议块与 Skill 结构化）
> - 用户决策：方案 A（五层全做）+ 多轮澄清 + 独立 PlanScene + 单 skill

## 1. 目标

把夜记的场景二从"纯聊天"升级为"生活助手"——让 Agent 能帮助用户规划生活。第一个真实 skill 是**计划 skill**：Agent 通过多轮对话理解用户的规划需求，生成结构化的计划提案（`::plan_proposal` 协议块），用户在前端采纳后落库为 Task/Plan 实体。

**核心承诺**：
- Agent **零写权限**——所有写入都通过用户在前端点"采纳"触发 REST API 完成
- Agent 的规划建议**必须附来源引用**（基于日记/记忆/画像的真实数据，不是泛泛模板）
- 危机意图下规划分支**直接短路**（沿用 P0 的 CrisisGuard，不可绕过）
- 协议块在会话内是**瞬时展示**（Agent 生成提案时），PlanScene 是**常驻管理**（用户主动查看）

**成功标准**：
- 用户说"我想养成早睡的习惯"，Agent 多轮澄清后生成带来源引用的 plan_proposal
- 用户在会话内点"采纳"，计划写入数据库，PlanScene 可见
- 危机关键词（"不想活"等）在规划意图下仍走安全短路，不进入规划流程
- PlanScene 能查看所有计划、今日待办、进度

## 2. 范围

### 五层垂直切片（全部 P2 内交付）

| 层 | 内容 | 备注 |
|----|------|------|
| L1 数据模型 | `Task` + `Plan` 表 + Alembic 迁移 + ORM | 报告 §P.2.1 |
| L2 REST API | `/api/v1/plans` + `/api/v1/tasks` 标准 CRUD | 前端采纳写回的入口 |
| L3 Agent 能力 | `plan_exploration` + `task_command` 意图 + PlannerAgent + 只读工具 | 报告 §P.2.2-P.2.4 |
| L4 协议块 | `PROTOCOL_BLOCK` SSE schema + `plan_proposal` / `task_proposal` / `clarification_request` 类型 | 复用 P0 已定义的事件类型 |
| L5 前端 | PlanScene（常驻查看） + 会话内协议块渲染（瞬时） + 采纳写回 | 报告 §P.2.5 |

### 本阶段包含
- 数据模型：`Plan`（容器）+ `Task`（单条待办）+ `source` 字段区分 manual/agent
- REST：CRUD + "今日待办"聚合接口
- 意图扩展：6→8 类（新增 `plan_exploration` / `task_command`）
- PlannerAgent：只读工具（`list_todos` / `get_plan_progress`）+ 多轮澄清 + `plan_proposal` 生成
- 协议块 SSE schema + 后端 `publish_protocol_block` 辅助函数
- 前端 PlanScene（计划看板 + 今日待办 + 进度）
- 前端会话内协议块渲染组件（卡片 + 采纳按钮 + 拒绝按钮）
- 危机短路在规划路径的强制约束
- 单元测试 + e2e 集成测试

### 本阶段不包含
- **重复任务（recurrence）**——MVP 只做单次待办
- **提醒推送**（push notification）——推迟到 P4+
- **日历集成**——推迟到 P4+
- **其他 skill**（情绪触发源、习惯追踪、关系动态等）——P2 只验证协议块扩展性用单 skill，多 skill 留 P3+
- **计划的记忆闭环回写**（source=task 的 episodic 写入）——报告 §P.2.5 提到的，但需要先有任务执行数据，推迟到 P3+ 闭环完善
- **周报"计划执行"段落**——同上，推迟

## 3. 架构设计

### 3.1 数据模型（L1）

新增两张表，放在 `server/app/infrastructure/models/plan.py`：

```python
class PlanRow(Base):
    __tablename__ = "plans"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # uuid hex
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    motivation: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 规划动机（Agent 生成的"为什么建议这个"，附来源引用）
    source_refs_json: Mapped[str] = mapped_column(Text, default="[]")
    # JSON: [{"type": "diary"|"episodic"|"memory", "id": ..., "date": ...}]
    status: Mapped[str] = mapped_column(String(20), default="active")
    # active / archived / completed
    source: Mapped[str] = mapped_column(String(20), default="manual")
    # manual / agent（区分用户手建 vs Agent 提案采纳）
    created_from_conversation_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)


class TaskRow(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    plan_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("plans.id"), nullable=True, index=True)
    # nullable：独立 task 不属于任何 plan
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_date: Mapped[date | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending / done / skipped
    source: Mapped[str] = mapped_column(String(20), default="manual")
    created_from_conversation_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)
```

**Alembic 迁移**：新增 `003_plan_task_domain.py`，创建两张表 + 索引。

### 3.2 REST API（L2）

新增 `server/app/api/v1/plan.py`：

| 方法 | 路径 | 用途 |
|------|------|------|
| POST | `/api/v1/plans` | 创建计划（手动 / 采纳 Agent 提案） |
| GET | `/api/v1/plans` | 列出当前用户的计划（可选 `status` 过滤） |
| GET | `/api/v1/plans/{id}` | 获取单个计划详情（含 tasks） |
| PATCH | `/api/v1/plans/{id}` | 更新计划（标题/状态） |
| DELETE | `/api/v1/plans/{id}` | 删除计划（级联删除 tasks） |
| POST | `/api/v1/tasks` | 创建单个 task（可独立于 plan） |
| GET | `/api/v1/tasks` | 列出 tasks（支持 `plan_id` / `status` / `due_date` 过滤） |
| GET | `/api/v1/tasks/today` | 今日待办聚合（due_date=today 或 无 plan 的 pending） |
| PATCH | `/api/v1/tasks/{id}` | 更新 task（状态切换 / 标记完成） |
| DELETE | `/api/v1/tasks/{id}` | 删除 task |

**关键约束**：
- 所有端点需要 `CurrentUserDep` 认证
- 所有查询强制 `user_id` 过滤（多租户隔离）
- `POST /plans` 和 `POST /tasks` 接收 `source` 字段（`manual` / `agent`）和 `created_from_conversation_id`，用于审计来源

### 3.3 意图扩展（L3 第一部分）

修改 `server/app/domain/agents/types.py`：

```python
class ChatIntent(str, Enum):
    CASUAL_CHAT = "casual_chat"
    EMOTIONAL_VENT = "emotional_vent"
    RETROSPECTIVE_QUERY = "retrospective_query"
    ADVICE_SEEKING = "advice_seeking"
    CRISIS_SIGNAL = "crisis_signal"
    ENTITY_QUERY = "entity_query"
    # P2 新增
    PLAN_EXPLORATION = "plan_exploration"  # 规划探索，heavy，多轮
    TASK_COMMAND = "task_command"          # 单 task 快路径，light
```

修改 `server/app/domain/agents/chat_intent_classifier.py`：

```python
_PLAN_EXPLORATION_KEYWORDS = (
    "帮我规划", "想养成", "想开始", "计划一下", "做个计划",
    "安排一下", "帮我安排", "想坚持", "想戒掉", "想改掉",
    "规划", "计划",  # 兜底（弱信号，需配合上下文）
)

_TASK_COMMAND_KEYWORDS = (
    "加到待办", "加个待办", "记一下待办",
    "提醒我",  # 注意：实际不做推送，只创建 task
    "完成了", "做完了", "标记完成",
)
```

**路由表扩展**（`_INTENT_ROUTING`）：
- `plan_exploration` → tier=heavy, need_tools=["list_todos", "get_plan_progress"], max_iterations=5（多轮）
- `task_command` → tier=light, need_tools=["list_todos"], max_iterations=2（快路径）

### 3.4 PlannerAgent（L3 第二部分）

新增 `server/app/domain/agents/planner_agent.py`。它**不是** MultiAgentGraph 的 Worker（场景二不用 graph），而是场景二 ConversationLoop 内的一个"规划子流程"，由 `plan_exploration` 意图触发。

**PlannerAgent 的职责**：
1. 读取上下文（日记 RAG + 记忆 + UserProfile + 当前 plan/task 状态）
2. 判断用户输入是否包含完整的"做什么（what）"和"怎么做（how）"
3. 信息不足时，生成 `clarification_request` 协议块（或纯文本提问）反问用户
4. 信息完整时，生成 `plan_proposal` 协议块（带来源引用 + 拆解的 tasks）
5. 危机检测——任何时候命中 CrisisGuard，短路回安全响应

**PlannerAgent 的只读工具**（加入 `tool_factory.build_tool_specs()`）：

```python
ToolSpec(
    name="list_todos",
    description="列出用户当前的待办任务（只读）。可用于了解用户已有的计划负荷。",
    parameters={
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["pending", "done", "all"], "default": "pending"},
            "plan_id": {"type": "string", "description": "可选：限定某个计划内的 tasks"},
        },
    },
),
ToolSpec(
    name="get_plan_progress",
    description="查询单个计划的执行进度（只读）。",
    parameters={
        "type": "object",
        "properties": {
            "plan_id": {"type": "string"},
        },
        "required": ["plan_id"],
    },
),
```

**关键约束**：这两个工具是**只读**的——Agent 没有任何"创建/修改/删除 task"的工具。所有写入都通过协议块 → 用户采纳 → 前端 REST 完成。

### 3.5 协议块 SSE Schema（L4）

P0 已在 `StreamingEventType` 中定义了 `PROTOCOL_BLOCK = "protocol_block"` 事件类型，但未消费。P2 定义其载荷 schema。

**事件结构**：
```python
{
    "type": "protocol_block",
    "trace_id": "...",
    "block": {
        "block_type": "plan_proposal" | "task_proposal" | "clarification_request",
        "block_id": "temp-uuid-...",
        "data": { ... }  # 类型相关
    }
}
```

**三种 block_type 的 data schema**：

```python
# plan_proposal —— 一组 tasks 的提案
{
    "title": "晚间放松例程",
    "motivation": "你最近三周日记里 5 次提到失眠，建立一个固定的睡前例程可能有帮助。",
    "source_refs": [
        {"type": "diary", "id": 123, "date": "2026-08-01", "snippet": "昨晚又失眠了..."},
        {"type": "episodic", "id": "m456", "snippet": "连续三天提到入睡困难"}
    ],
    "tasks": [
        {"title": "睡前 30 分钟不看手机", "note": "可以从今天开始", "due_date": null},
        {"title": "泡一杯洋甘菊茶", "note": null, "due_date": null}
    ],
    "status": "awaiting_confirmation"
}

# task_proposal —— 单个 task 的快路径提案（task_command 意图触发）
{
    "title": "写报告",
    "note": null,
    "due_date": "2026-08-10",
    "plan_id": null,  # 可选：归属某 plan
    "status": "awaiting_confirmation"
}

# clarification_request —— 多轮澄清的反问
{
    "question": "早睡是个很好的目标！你希望具体怎么实现呢？比如设定一个固定的睡觉时间，或者做一些睡前放松？",
    "missing_fields": ["how"],  # 告诉前端缺什么
    "context": {"what": "早睡"}  # 已收集到的信息
}
```

**后端发布辅助**（新增到 `server/app/shared/streaming_events.py`）：

```python
async def publish_protocol_block(
    trace_id: str,
    *,
    block_type: str,
    block_id: str,
    data: dict[str, Any],
) -> None:
    """发布一个 PROTOCOL_BLOCK 事件。"""
    bus = get_event_bus()
    await bus.publish(
        trace_id,
        {
            "type": StreamingEventType.PROTOCOL_BLOCK,
            "trace_id": trace_id,
            "block": {
                "block_type": block_type,
                "block_id": block_id,
                "data": data,
            },
        },
    )
```

### 3.6 多轮澄清流程（L3 第三部分）

`plan_exploration` 意图触发后的完整流程：

```
Turn 1:
  用户："我想养成早睡的习惯"
  → ChatIntent 分类：plan_exploration
  → ConversationLoop 进入 PlannerAgent 子流程
  → PlannerAgent 判断：what="早睡"，how=缺失
  → 生成 clarification_request 协议块
  → 前端渲染反问卡片 + 文本气泡（"早睡是个好目标..."）
  → 轮次结束（不生成 plan_proposal）

Turn 2:
  用户："我想 11 点前睡，睡前不看手机"
  → ChatIntent 分类：plan_exploration（继续）
  → PlannerAgent 读取上一轮的 context（what=早睡）
  → 判断：what=早睡, how=11点前睡+不看手机 → 信息完整
  → 调用 list_todos 工具了解现状（发现已有 2 个 pending task）
  → 检索相关日记/记忆（找"失眠"相关条目作为 source_refs）
  → 生成 plan_proposal 协议块（带来源引用）
  → 前端渲染提案卡片（标题+动机+tasks+采纳/拒绝按钮）
  → 轮次结束

Turn 3a（采纳）:
  用户：在 PlanScene 或会话内点"采纳"
  → 前端 POST /api/v1/plans + 关联 POST /api/v1/tasks（source="agent"）
  → 计划落库，PlanScene 可见
  → 前端更新卡片状态为"已采纳"

Turn 3b（拒绝/修改）:
  用户：点"拒绝" → 卡片消失，无任何写入
  或：点"修改" → 进入编辑模式，用户调整后采纳
```

**信息完整度判断**（PlannerAgent 内）：
- `what`（做什么）：必须存在——用户说了想达成的目标
- `how`（怎么做）：可选但鼓励——具体执行步骤
- `when`（何时）：可选——默认无 due_date
- 如果 `what` 缺失 → clarification_request 询问目标
- 如果 `how` 缺失 → clarification_request 询问方法（用户提供 or Agent 建议）

**关键约束**：PlannerAgent 的 prompt 明确要求"建议必须附来源引用"——没有真实数据支撑时，motivation 字段为空或诚实说明"这是基于你这次对话的建议，暂无历史数据支撑"。

### 3.7 危机短路（强约束）

PlannerAgent 子流程在**两个检查点**做危机检测：

1. **入口检查**：`plan_exploration` 意图触发时，先跑 `CrisisGuard.detect(user_input)`。命中则不进入规划流程，走 P0 的安全短路路径。
2. **生成前检查**：生成 `plan_proposal` 前，对 proposal 的 `motivation` + `tasks` 文本再跑一次 CrisisGuard，避免 LLM 在建议里生成有害内容。

**设计语言约束**（报告定位张力）：
- PlannerAgent prompt 禁止使用"必须""应该""一定要完成"等施压措辞
- 任务标题避免使用红色感叹号 / "逾期" / "未完成"等负面词
- UI 弱化逾期状态——`due_date` 过期只显示"已过截止日"，不变红

### 3.8 前端架构（L5）

#### 3.8.1 PlanScene（新增，常驻管理页）

新增 `src/features/plan/PlanScene.vue`（路由 `/plan`）：

- **今日待办**区块：调用 `GET /api/v1/tasks/today`，展示今日到期或无 plan 的 pending tasks
- **计划看板**区块：调用 `GET /api/v1/plans`，每个计划卡片展示 title / motivation / 进度条（done/total） / task 列表
- **独立 task 区块**：无 plan_id 的独立 tasks 单列展示
- 操作：勾选完成 / 删除 / 编辑 / 新建计划 / 新建 task

**导航入口**：在 `HomeScene` 顶部加"我的计划"入口卡片，或在主导航栏加 `/plan` 项。

#### 3.8.2 会话内协议块渲染（瞬时展示）

修改 `src/features/chat/` 下的组件：

- **新增组件** `PlanProposalCard.vue`——渲染 `plan_proposal` 协议块，含采纳/拒绝/修改按钮
- **新增组件** `TaskProposalCard.vue`——渲染 `task_proposal`，单行确认
- **新增组件** `ClarificationCard.vue`——渲染 `clarification_request`，展示反问 + 已收集信息
- **修改** `useStreamingReply.ts`：维护"渲染段"数组（替代纯字符串拼接），`TEXT_DELTA` 累积成文本段，`PROTOCOL_BLOCK` 作为独立段插入
- **修改** `ChatMessage.vue`：按渲染段顺序渲染（文本气泡 + 协议块卡片）

**采纳写回流程**：
```
用户点"采纳"
→ PlanProposalCard 调用 POST /api/v1/plans（source="agent", created_from_conversation_id=当前会话id）
→ 批量 POST /api/v1/tasks（plan_id=新建的plan_id）
→ 成功后：卡片状态变"已采纳"，发送 chat 消息告知用户"已添加到计划"
→ 失败：卡片显示错误，允许重试
```

#### 3.8.3 渲染段数据模型

`useStreamingReply.ts` 的核心改动：

```typescript
type RenderSegment =
  | { kind: 'text'; content: string }
  | { kind: 'protocol_block'; blockType: string; blockId: string; data: any; status: 'pending' | 'accepted' | 'rejected' }

const segments = ref<RenderSegment[]>([])
let currentTextSegment = ''

// TEXT_DELTA: 累积到 currentTextSegment
// PROTOCOL_BLOCK: 先 flush currentTextSegment 为一个 text segment，再 push 协议块 segment
// REPLY_END: flush 最后的 text segment
```

**注意**：这和 P0 的"纯字符串 replyText"模型不同。P0 的 `replyText` ref 保留（向后兼容，渲染历史消息用），但流式渲染期间用 segments 数组。

## 4. 数据流

### 4.1 多轮规划完整流（plan_exploration）

```
Turn 1: "我想养成早睡的习惯"
  → POST /conversations/{id}/messages/stream
  → ConversationLoop Stage 1-3（危机检测通过）
  → Stage 4 ChatIntent: plan_exploration
  → 进入 PlannerAgent 子流程
    → 信息完整度判断：缺 how
    → publish_protocol_block(clarification_request, {question, missing_fields:["how"]})
  → publish_reply_end
  → 前端：ClarificationCard 渲染

Turn 2: "11点前睡，睡前不看手机"
  → 同上路径
  → PlannerAgent 读取 SessionContext（上一轮的 clarification + context）
    → 信息完整
    → list_todos 工具调用（了解现状）
    → RAG 检索相关日记（"失眠"相关，作为 source_refs）
    → publish_protocol_block(plan_proposal, {title, motivation, source_refs, tasks})
  → publish_reply_end
  → 前端：PlanProposalCard 渲染（带采纳按钮）

Turn 3: 用户点"采纳"
  → 前端 POST /api/v1/plans {title, motivation, source_refs, source:"agent", created_from_conversation_id}
  → 前端批量 POST /api/v1/tasks {plan_id, title, ...}
  → 卡片状态 → accepted
```

### 4.2 单 task 快路径（task_command）

```
用户："把明天写报告加到待办"
  → ChatIntent: task_command（light tier）
  → ConversationLoop Stage 4 直接提取信息（what=写报告, when=明天）
  → publish_protocol_block(task_proposal, {title:"写报告", due_date:tomorrow})
  → 前端：TaskProposalCard 单行确认
  → 用户点采纳 → POST /api/v1/tasks
```

### 4.3 危机短路

```
用户："我不想活了，帮我规划一下"
  → ChatIntent: 可能是 plan_exploration 或 crisis_signal（取决于规则优先级）
  → ConversationLoop Stage 2 危机检测命中
  → 短路到 CrisisGuard 安全响应，不进入规划流程
  → publish_text_delta(安全模板) → publish_reply_end
```

## 5. 错误处理

| 场景 | 处理 |
|------|------|
| 用户点采纳但 REST API 失败 | 卡片显示错误 + 重试按钮，不自动重试 |
| PlannerAgent 信息不足且用户连续 3 轮没补全 | 第 3 轮后 Agent 主动建议："要不我们先从 [具体建议] 开始？" 并生成 proposal |
| PlannerAgent 检索不到相关日记（source_refs 为空） | motivation 诚实说明"基于本次对话的建议"，source_refs 为空数组 |
| 危机信号在规划中途出现 | 立即短路，发 RETRACT + 安全模板（复用 P0 防线） |
| plan_proposal 超长（tasks 太多） | PlannerAgent prompt 约束最多 5 个 tasks，避免认知过载 |

## 6. 测试策略

### 6.1 后端单元测试

| 测试文件 | 覆盖范围 |
|---------|---------|
| `tests/unit/infrastructure/test_plan_models.py`（新增） | Plan/Task ORM 增删改查、级联删除、user_id 隔离 |
| `tests/unit/api/test_plan_routes.py`（新增） | REST CRUD、今日待办聚合、认证、多租户隔离 |
| `tests/unit/domain/agents/test_planner_agent.py`（新增） | 信息完整度判断、多轮澄清、source_refs 提取、危机短路 |
| `tests/unit/domain/agents/test_chat_intent_classifier.py`（扩展） | plan_exploration / task_command 关键词命中 |
| `tests/unit/services/ai/test_tool_factory.py`（扩展） | list_todos / get_plan_progress 只读工具 |
| `tests/unit/shared/test_streaming_events.py`（扩展） | publish_protocol_block 事件结构 |

### 6.2 前端测试

| 测试文件 | 覆盖范围 |
|---------|---------|
| `useStreamingReply.spec.ts`（扩展） | segments 数组、TEXT_DELTA + PROTOCOL_BLOCK 混排 |
| `PlanProposalCard.spec.ts`（新增） | 采纳/拒绝按钮、API 调用、状态切换 |
| `PlanScene.spec.ts`（新增） | 计划列表、今日待办、完成切换 |

### 6.3 e2e 集成测试

| 测试文件 | 覆盖范围 |
|---------|---------|
| `tests/e2e/test_plan_skill_flow.py`（新增） | 端到端：多轮对话 → plan_proposal → 采纳 → PlanScene 可见 |

### 6.4 Eval 闸门

P2 合并前必须通过现有 eval 基线（RAG + generation），确保新增意图和 PlannerAgent 不破坏现有场景二的生成质量。

## 7. 实施顺序（按依赖关系）

### 第一周：基础设施（L1-L2-L4）
1. **数据模型 + 迁移**（Plan/Task 表）
2. **REST API**（CRUD + 今日待办）
3. **协议块 SSE schema + publish_protocol_block**

### 第二周：Agent 能力（L3）
4. **意图扩展**（ChatIntent 6→8 + 规则关键词 + 路由表）
5. **只读工具**（list_todos / get_plan_progress）
6. **PlannerAgent**（信息完整度判断 + 多轮澄清 + plan_proposal 生成 + 危机短路）

### 第三周：前端 + 集成（L5 + 测试）
7. **PlanScene**（计划看板 + 今日待办）
8. **会话内协议块渲染**（PlanProposalCard / TaskProposalCard / ClarificationCard + segments 模型）
9. **采纳写回流程**（前端 → REST → 状态更新）
10. **e2e 测试 + eval 闸门验证**

## 8. 验证清单

### 数据模型
- [ ] PlanRow + TaskRow ORM 定义
- [ ] Alembic 迁移 003
- [ ] 级联删除（删 plan 删其下 tasks）

### REST API
- [ ] /api/v1/plans CRUD + 多租户隔离
- [ ] /api/v1/tasks CRUD
- [ ] /api/v1/tasks/today 聚合接口
- [ ] source 字段审计（manual / agent）

### Agent 能力
- [ ] ChatIntent 扩展 8 类
- [ ] ChatIntentClassifier 关键词规则
- [ ] list_todos / get_plan_progress 工具
- [ ] PlannerAgent 信息完整度判断
- [ ] PlannerAgent 多轮澄清（clarification_request）
- [ ] PlannerAgent plan_proposal 生成（带 source_refs）
- [ ] PlannerAgent 危机短路（入口 + 生成前双检查）

### 协议块
- [ ] publish_protocol_block 辅助函数
- [ ] plan_proposal / task_proposal / clarification_request 三种 schema

### 前端
- [ ] PlanScene（计划看板 + 今日待办 + 完成/删除）
- [ ] 导航入口（HomeScene 或主导航）
- [ ] useStreamingReply segments 模型（TEXT_DELTA + PROTOCOL_BLOCK 混排）
- [ ] PlanProposalCard（采纳/拒绝/修改 + REST 写回）
- [ ] TaskProposalCard（单行确认）
- [ ] ClarificationCard（反问展示）
- [ ] ChatMessage 渲染段顺序

### 验证
- [ ] 所有单元测试通过
- [ ] e2e 多轮规划流测试通过
- [ ] 现有 eval 基线不退化
- [ ] 危机关键词在规划意图下仍短路

## 9. 风险与缓解

| 风险 | 缓解 |
|------|------|
| PlannerAgent 的多轮澄清让用户觉得啰嗦 | 第 3 轮强制收口；prompt 约束反问语气温柔 |
| 协议块 segments 模型改动大，破坏 P0/P1 的 replyText | 保留 replyText ref 兼容历史消息渲染；流式期间用 segments |
| 计划功能引入"压力感"违反心理陪伴定位 | UI 弱化逾期、避免红色告警、PlannerAgent prompt 禁施压措辞 |
| LLM 生成无来源引用的泛泛建议 | prompt 强制 source_refs；无数据时诚实说明 |
| task_command 误触发（"完成了"在非待办语境） | 关键词匹配 + 上下文校验（检查是否已有相关 task） |
