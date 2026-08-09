# V3 P3: 计划闭环 + 真实流式

> **阶段**: P3（V3 路线图第三阶段）
> **工期**: 1.5-2 周
> **前置依赖**: P0 + P1 + P2 已合并到 main（commit `7eba01a`）
> **设计来源**:
> - V3 分析报告 §P.2.5（记忆/反馈闭环扩展）
> - P2 spec 中推迟到 P3+ 的内容
> - 用户决策：去掉 Thompson Sampling（无用户验证，需 A/B 测试）

## 1. 目标

深化 P2 计划 skill 的闭环能力，并把 P0 的"模拟流式"升级为真正的 LLM token 级流式。三项交付：

1. **记忆闭环回写**——任务完成/放弃作为 source=task 的情景记忆写入，让 Agent 能"记住"用户的执行历史
2. **周报"计划执行"段落**——InsightAgent 在周报里回顾本周计划完成情况
3. **真实 LLM astream 端到端**——把 `generate_reply_streaming` 从"先跑完同步管线再分块推送"升级为真正的 token 级流式

**成功标准**:
- 用户在 PlanScene 标记任务完成后，episodic memory 多一条 source=task 的记忆
- 周报自动包含"✅ 计划执行回顾"段落，引用真实的 plan/task 数据
- 流式回复首 token 延迟从"等完整回复生成完"降到"LLM 开始输出的第一个 token"

## 2. 范围

### 本阶段包含
1. `UnifiedMemoryAtom.source` 枚举扩展：diary/chat/card → +task
2. `ContentNormalizer.from_task()` ——任务完成时生成 source=task 的记忆原子
3. `plan_service.update_task_status` 在状态变更时触发记忆回写
4. `weekly_service._build_weekly_content` 注入 plan/task 数据块
5. `INSIGHT_REPORT_SYSTEM` prompt 新增"计划执行回顾"段落指引
6. `generate_reply_streaming` 重构：提取 `_prepare_reply_context()` 前置函数（方案 B，只改流式路径），流式路径改用 `run_conversation_loop_streaming`
7. `TracingLLMClient._record_streaming` 修复 token 统计丢失
8. **场景一流式**——单 content worker 路径（PURE_RECORD / EMOTIONAL_SUPPORT / HABIT_TRACKING，占 75%）走 astream；多 worker 路径（RETROSPECTIVE_REVIEW）保持非流式
9. PlannerAgent 前置文本流式——调用 ainvoke 生成 JSON 前先流式发一句过渡语，优化等待体验
10. 单元测试 + e2e 测试 + 流式/非流式一致性测试

### 本阶段不包含
- **Thompson Sampling 规划风格反馈**——用户明确去掉（无用户验证，需 A/B 测试，推迟到有用户基础后）
- **PlannerAgent 改 astream**——JSON 结构化输出不适合流式解析（详见 §3.5），保持一次性 ainvoke，仅加前置文本流式优化体验
- **多 worker 路径的场景一流式**（RETROSPECTIVE_REVIEW 的 empathy+insight 合成）——synthesize 步骤需要完整输入，保持非流式
- **重复任务 / 提醒推送 / 日历集成**——继续推迟
- **记忆检索时对 source=task 的特殊加权**——task 记忆和 diary/chat 记忆平等参与检索，不做特殊处理

## 3. 架构设计

### 3.1 记忆闭环回写

#### source 枚举扩展

`server/app/domain/memory/atom.py` 第 21 行：

```python
# 改前
Source = Literal["diary", "card", "chat"]
# 改后
Source = Literal["diary", "card", "chat", "task"]
```

`EpisodicEntry.source`（`types.py:25`）已是 `str` 无枚举校验，无需改。ORM `EpisodicMemoryRow` 的 source 在 `payload_json` 内，**无需迁移**。

#### ContentNormalizer.from_task()

在 `server/app/services/normalizer.py` 新增类方法（仿现有 `from_conversation`）：

```python
@classmethod
def from_task(
    cls,
    task_title: str,
    task_note: str | None,
    plan_title: str | None,
    status: str,  # "done" | "skipped"
    user_id: str,
) -> UnifiedMemoryAtom:
    """从任务状态变更生成记忆原子。

    importance 必须设 ≥ 0.6 以通过四维门控的 emotional_significance
    检查（task 完成通常情绪中性 mood_score=0.5，不满足
    abs(mood_score-0.5)>=0.15，必须靠 importance>=0.4 兜底）。
    """
    action = "完成了" if status == "done" else "跳过了"
    plan_ctx = f"（计划「{plan_title}」）" if plan_title else ""
    event_summary = f"{action}任务「{task_title}」{plan_ctx}"

    return UnifiedMemoryAtom(
        source="task",
        user_id=user_id,
        event_summary=event_summary,
        emotion="neutral",
        tags=["task", status] + ([plan_title] if plan_title else []),
        mood_score=0.5,  # 中性
        importance=0.6,  # 强制高于门控阈值 0.4
        raw_content=task_note or task_title,
        event_date=datetime.utcnow(),
    )
```

#### plan_service 触发回写

`server/app/services/plan_service.py` 的 `update_task_status`：

```python
def update_task_status(
    db: Session, *, task_id: str, user_id: str, status: str,
    container: ServiceContainer | None = None,  # 新增可选参数
) -> TaskRow:
    row = get_task(db, task_id=task_id, user_id=user_id)
    old_status = row.status
    row.status = status
    if status == "done":
        row.completed_at = datetime.utcnow()
    else:
        row.completed_at = None
    db.commit()
    db.refresh(row)

    # 状态变更到终态（done/skipped）时触发记忆回写
    if container is not None and old_status != status and status in ("done", "skipped"):
        _persist_task_memory(db, row, container, user_id)

    return row


def _persist_task_memory(
    db: Session, task: TaskRow, container: ServiceContainer, user_id: str
) -> None:
    """将任务状态变更写入 episodic memory（best-effort，失败不阻塞）。"""
    import contextlib
    from app.services.normalizer import ContentNormalizer

    try:
        plan_title = None
        if task.plan_id:
            plan = db.get(PlanRow, task.plan_id)
            plan_title = plan.title if plan else None

        atom = ContentNormalizer.from_task(
            task_title=task.title,
            task_note=task.note,
            plan_title=plan_title,
            status=task.status,
            user_id=user_id,
        )
        # 通过 container 获取 MemoryGateway（和场景二一致）
        gateway = container.memory_gateway
        gateway.persist_atom(db, atom)
    except Exception as exc:
        logger.warning("Task memory persist failed (non-fatal): %s", exc)
```

**API 层改造**：`server/app/api/v1/plan.py` 的 `update_task` 端点需要把 `container` 传给 `update_task_status`：

```python
@tasks_router.patch("/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: str, body: TaskUpdateRequest,
    db: DbDep, user: CurrentUserDep, container: ContainerDep,  # 新增
) -> TaskResponse:
    ...
    if "status" in fields:
        task = plan_service.update_task_status(
            db, task_id=task_id, user_id=str(user.id),
            status=fields.pop("status"),
            container=container,  # 传入
        )
```

### 3.2 周报"计划执行"段落

#### weekly_service 注入 plan 数据

`server/app/services/weekly_service.py` 的 `_build_weekly_content` 函数，在组装 content 文本时追加 plan 数据块：

```python
def _build_weekly_content(
    self, start: date, end: date,
    diaries: list, cards: list,
    plans_data: dict | None = None,  # 新增参数
) -> str:
    # ... 现有日记/卡片内容组装 ...

    # 追加计划执行数据块
    if plans_data and (plans_data.get("active_plans") or plans_data.get("week_tasks")):
        lines.append("\n\n【本周计划执行】")
        for plan in plans_data.get("active_plans", []):
            done = sum(1 for t in plan.tasks if t.status == "done")
            total = len(plan.tasks)
            lines.append(f"- 计划「{plan.title}」：{done}/{total} 完成")
        for task in plans_data.get("week_tasks", []):
            status_mark = "✓" if task.status == "done" else "○"
            lines.append(f"- {status_mark} {task.title}")

    return "\n".join(lines)
```

`create_weekly_report` 在调用 `_build_weekly_content` 前，查询本周范围内的 plan/task：

```python
def create_weekly_report(self, db, container, user_id, reference=None):
    start, end = self._week_bounds(reference)
    diaries = self._diaries_in_week(db, user_id, start, end)
    cards = self._cards_in_week(db, user_id, start, end)

    # 新增：查询本周 plan/task
    plans_data = self._plans_in_week(db, user_id, start, end)

    content = self._build_weekly_content(start, end, diaries, cards, plans_data)
    # ... 后续不变 ...
```

新增辅助方法 `_plans_in_week`：

```python
def _plans_in_week(self, db, user_id, start, end):
    """查询本周相关的 plan/task（创建或完成在本周内的）。"""
    from app.services import plan_service
    plans = plan_service.list_plans(db, user_id=user_id, status="active")
    # 筛选本周内有活动的 plan（有 task 在本周完成/创建）
    week_tasks = []
    active_plans = []
    for plan in plans:
        plan_week_tasks = [
            t for t in plan.tasks
            if t.created_at and start <= t.created_at.date() <= end
            or (t.completed_at and start <= t.completed_at.date() <= end)
        ]
        if plan_week_tasks:
            active_plans.append(plan)
            week_tasks.extend(plan_week_tasks)
    # 加上独立 task（无 plan_id）
    standalone = plan_service.list_tasks(db, user_id=user_id, status=None)
    for t in standalone:
        if t.plan_id is None and (
            (t.created_at and start <= t.created_at.date() <= end)
            or (t.completed_at and start <= t.completed_at.date() <= end)
        ):
            week_tasks.append(t)
    return {"active_plans": active_plans, "week_tasks": week_tasks}
```

#### prompt 新增段落指引

`server/app/domain/agents/prompts.py` 的 `INSIGHT_REPORT_SYSTEM`，在第4段（💡 个性化建议）之后追加：

```python
INSIGHT_REPORT_SYSTEM = """...（现有内容）...

5. ✅ 计划执行回顾
   - 如果「本周计划执行」数据块有内容，总结完成情况（如"本周完成了 X/Y 个计划"）
   - 对坚持的习惯给予肯定，对未完成的用温和语气（避免施压）
   - 如果没有计划数据，跳过此段
"""
```

### 3.3 真实 LLM astream 端到端（核心重构）

#### 问题回顾

P0 的 `generate_reply_streaming` 走"模拟流式"：先调用同步 `generate_reply`（跑完危机检测、工具调用、记忆回写等全部 370 行逻辑），再把结果文本按 20 字符分块 + 20ms 间隔推送。用户看到的"流式"其实是假流式——首 token 延迟等于完整生成延迟。

`run_conversation_loop_streaming`（P0 加的）已实现真正的 astream（工具轮 invoke + 最终回复 astream + 安全守卫），但**只被测试调用，未接入生产**。

#### 方案 B：只改流式路径（采纳）

从 `generate_reply` 的 370 行中提取 Stage 1-3（前置上下文准备）为独立函数 `_prepare_reply_context()`，**只供流式路径使用**。非流式 `generate_reply` 保持原样不动（降低回归风险）。

为防止两份代码 drift，新增一个**一致性测试**：断言 `_prepare_reply_context` 的产出和 `generate_reply` 内部对应阶段的中间状态一致。

**为何不选方案 A（两条路径都重构）**：P3 的核心目标是升级流式，不是重构 generate_reply。方案 A 把变更面扩大一倍，600+ 测试的回归风险不值得。如果半年后 Stage 1-3 真的需要改，那时再统一重构。

```python
# server/app/services/conversation_ai_service.py

@dataclass
class ReplyContext:
    """generate_reply 的 Stage 1-3 产出，供流式/非流式路径共用。"""
    conversation_id: str
    content: str
    intent_result: ChatIntentResult | None
    pinned_diaries_text: str
    retrieved_diaries_text: str
    retrieved_diary_ids: list[int]
    episodic_text: str
    memory_ids: list[str]
    tools: dict[str, ToolFn] | None
    crisis_guard: CrisisGuard | None
    is_crisis: bool
    safe_response: str | None  # 危机短路时的安全模板
    trace_id: str


def _prepare_reply_context(
    db: Session,
    container: ServiceContainer,
    *,
    conversation_id: str,
    content: str,
    diary_ids: list[int],
    user_id: str,
    auto_retrieve: bool,
    crisis_guard: CrisisGuard | None,
    trace_id: str | None,
) -> ReplyContext:
    """提取 generate_reply 的 Stage 1-3（危机检测、意图分类、RAG、上下文组装）。

    流式路径（generate_reply_streaming）和非流式路径（generate_reply）
    共用此函数，保证前置逻辑一致性。
    """
    # ── 从 generate_reply 第 206-440 行提取 ──
    # Stage 2: 危机前置检测
    # Stage 2.1: session routing（只读，不写）
    # Stage 2.5: 意图分类
    # Stage 2.5b: 槽位抽取
    # Stage 2.6: 技能选择+执行（analysis 类直接执行）
    # Stage 3: RAG 检索 + episodic 加载
    # 返回 ReplyContext，不执行 Stage 4-5
    ...
```

#### generate_reply_streaming 重构

```python
async def generate_reply_streaming(...) -> None:
    """真实流式版本（P3 升级）。

    替代 P0 的模拟流式：前置上下文 → 真正的 astream → 后置回写。
    """
    from app.services.ai.conversation_loop import run_conversation_loop_streaming
    from app.shared.streaming_events import (
        publish_reply_end, publish_reply_start,
        publish_text_delta, publish_retract,
    )

    reply_started = False
    reply_end_sent = False
    final_reply_text = ""  # 用于后置记忆回写

    try:
        # Stage 1-3：前置上下文
        ctx = _prepare_reply_context(
            db, container,
            conversation_id=conversation_id,
            content=content,
            diary_ids=diary_ids,
            user_id=user_id,
            auto_retrieve=auto_retrieve,
            crisis_guard=crisis_guard,
            trace_id=trace_id or None,
        )

        if not trace_id:
            return

        # 危机短路
        if ctx.is_crisis:
            await publish_reply_start(trace_id, intent="crisis_signal")
            reply_started = True
            await publish_text_delta(trace_id, ctx.safe_response or "")
            await publish_reply_end(trace_id)
            reply_end_sent = True
            return

        # Stage 4：真正的 astream
        async for item in run_conversation_loop_streaming(
            db=db,
            container=container,
            conversation_id=conversation_id,
            content=content,
            pinned_diaries_text=ctx.pinned_diaries_text,
            retrieved_diaries_text=ctx.retrieved_diaries_text,
            episodic_text=ctx.episodic_text,
            memory_ids=ctx.memory_ids,
            tools=ctx.tools,
            crisis_guard=ctx.crisis_guard,
            user_id=user_id,
            intent_result=ctx.intent_result,
            trace_id=trace_id,
        ):
            if isinstance(item, str):
                final_reply_text += item
            # run_conversation_loop_streaming 自己发 TEXT_DELTA/RETRACT
            # 这里只是消费 yield 的内容用于后置回写

        reply_end_sent = True  # loop_streaming 已发 REPLY_END

        # Stage 5：后置回写（用聚合的 final_reply_text）
        _maybe_persist_episodic(db, container, conversation_id, content, final_reply_text, user_id)
        # ... 风格反馈 + 实体提取 ...

    except asyncio.CancelledError:
        if reply_started and not reply_end_sent and trace_id:
            with contextlib.suppress(Exception):
                await publish_reply_end(trace_id, error="cancelled")
            reply_end_sent = True
        raise
    except Exception as exc:
        logger.exception("Streaming reply failed: %s", exc)
        # ... P1 的 terminating_reply 兜底 ...
    finally:
        if trace_id and reply_started and not reply_end_sent:
            with contextlib.suppress(Exception):
                await publish_reply_end(trace_id, error="finalized")
```

#### TracingLLMClient token 统计修复

`server/app/shared/tracing_llm.py` 的 `_record_streaming` 当前创建的 `_Msg.response_metadata = {}`，导致 token 统计丢失。修复：

```python
def _record_streaming(self, prompt: str, full_text: str, started: float, error: str | None) -> None:
    """Record a streaming LLM call with best-effort token estimation."""

    class _Msg:
        def __init__(self, content: str) -> None:
            self.content = content
            # 估算 token 数（粗略：中文按字符数，英文按 4 字符/token）
            estimated_tokens = max(1, len(content) // 3)
            self.response_metadata = {
                "token_usage": {
                    "prompt_tokens": max(1, len(prompt) // 3),
                    "completion_tokens": estimated_tokens,
                    "total_tokens": max(1, len(prompt) // 3) + estimated_tokens,
                }
            }

    self._record(prompt, _Msg(full_text), started, error)
```

注意：这是**估算**，不是真实 token 数（真实需要 tokenizer）。但比全零好——usage 统计、token 成本追踪至少有参考值。字段名 `token_usage` 要和现有 `extract_token_usage` 函数的解析逻辑一致（确认 `app/services/ai/utils.py` 的 `extract_token_usage` 读哪个 key）。

### 3.4 场景一流式（单 worker 路径）

#### 架构分析

场景一（日记→AI 回信）的 `MultiAgentGraph` 按 `INTENT_ROUTING` 路由 worker：

| 意图 | Workers | Content Workers 数 | synthesize 方式 |
|------|---------|-------------------|----------------|
| PURE_RECORD | empathy | 1 | 直接返回（第 261 行） |
| EMOTIONAL_SUPPORT | empathy + retrieval | 1（retrieval 被过滤） | 直接返回 |
| RETROSPECTIVE_REVIEW | empathy + retrieval + insight | 2 | LLM synthesize |
| HABIT_TRACKING | retrieval + insight | 1 | 直接返回 |

**4 种意图里 3 种（75%）是单 content worker 路径**——synthesize 跳过 LLM 合成，直接返回 worker 输出。这些路径可以流式化。

#### 实现方案

在 `server/app/domain/agents/supervisor.py` 新增流式合成方法 `synthesize_streaming`：

```python
async def synthesize_streaming(
    self, outputs: dict[str, str], state: Any, *, trace_id: str = ""
) -> AsyncGenerator[str | dict, None]:
    """流式版本的 synthesize。

    单 content worker 路径：直接 astream 那个 worker 的回复。
    多 content worker 路径：降级为非流式（调 synthesize 后一次性 yield）。

    yields:
        str → TEXT_DELTA 内容（调用方发布到 TraceEventBus）
        dict → {"reply_end": True} 等信号
    """
    content_outputs = {k: v for k, v in outputs.items() if k != "retrieval"}

    if len(content_outputs) == 1:
        # 单 worker 路径——让 worker 重新 astream
        worker_name = next(iter(content_outputs.keys()))
        worker = self._workers.get(worker_name)
        if worker is not None and hasattr(worker, "run_streaming"):
            # Worker 支持流式——逐 token yield
            async for token in worker.run_streaming(state, trace_id=trace_id):
                yield token
            return
        # Worker 不支持流式——降级为一次性返回已有输出
        yield content_outputs[worker_name]
        return

    # 多 worker 路径——降级为非流式 synthesize
    result = await self.synthesize(outputs, state)
    yield result["final_response"]
```

#### Worker 流式方法

EmpathyAgent 和 InsightAgent 新增 `run_streaming` 方法（与 `run` 并行，不破坏现有路径）：

```python
# EmpathyAgent（同理 InsightAgent）
async def run_streaming(self, state: Any, *, trace_id: str = "") -> AsyncGenerator[str, None]:
    """流式版本——重新构建 prompt 并 astream。

    与 run() 共用 prompt 构建逻辑（提取为 _build_prompt），但用 astream
    替代 ainvoke。SafetyGuard 过滤由调用方（场景二）或此处内联（场景一）
    处理——场景一复用 P0 的 StreamingSafetyGuard。
    """
    from app.shared.streaming_safety import StreamingSafetyGuard
    from app.shared.crisis_guard import CrisisGuard

    prompt = self._build_prompt(state)  # 提取的共用方法
    guard = StreamingSafetyGuard(CrisisGuard())

    async def _raw_stream():
        async for token in self._llm.astream(prompt):
            yield token

    async for item in guard.filter_stream(_raw_stream(), intent="emotional_vent"):
        if isinstance(item, str):
            yield item
        # RETRACT 在场景一由调用方处理（前端 segments 模型）
```

#### 场景一流式入口

`server/app/services/analysis_service.py` 的分析触发逻辑，新增流式变体。当 trace_id 存在时走流式：

```python
async def trigger_analysis_streaming(
    self, db, container, diary_id, user_id, *, trace_id: str
) -> None:
    """场景一流式版本——复用 MultiAgentGraph 但用 synthesize_streaming。"""
    # ... 前置 Retrieval/Empathy/Insight worker 并发执行（不变）...
    # synthesize 阶段改为：
    async for token in supervisor.synthesize_streaming(outputs, state, trace_id=trace_id):
        if isinstance(token, str):
            await publish_text_delta(trace_id, token)
    await publish_reply_end(trace_id)
```

**关键约束**：
- 场景一流式只在 trace_id 存在时触发（和场景二一样的灰度模式）
- 多 worker 路径（RETROSPECTIVE_REVIEW）自动降级为非流式 synthesize，用户体验是"等一下然后一次性显示"
- Worker 的 `run_streaming` 和 `run` 共用 `_build_prompt`，不重复 prompt 逻辑

### 3.5 PlannerAgent 前置文本流式

#### 为什么不改 astream（技术约束）

PlannerAgent 生成的是 JSON 协议块。流式 JSON 的核心问题：

1. **无法增量解析**：JSON 是严格嵌套结构，`{"title": "早睡` 收到一半时无法确定 title 的值，只能等完整 JSON 到齐再 `json.loads`——和一次性 ainvoke 无区别。
2. **前端无法增量渲染**：协议块是一个完整 UI 单元（一张卡片）。title 来了但 tasks 没来，卡片无法画——用户看到残缺闪烁的卡片，体验比等待更差。
3. **流式 JSON 解析器**（ijson 等）对 LLM 输出容错差，复杂度高收益低。

#### 优化方案：前置过渡语文本流式

在 PlannerAgent 调用 ainvoke 生成 JSON 之前，先流式发一句过渡语，让用户知道 Agent 在工作：

```python
# planner_agent.py 的 _emit_plan_proposal 方法

async def _emit_plan_proposal(self, inp, completeness):
    # 先流式发过渡语（基于 completeness 判断语境）
    transition = self._build_transition_text(completeness)
    await publish_text_delta(inp.trace_id, transition)
    await publish_text_end(inp.trace_id)

    # 然后调用 ainvoke 生成 JSON（非流式）
    response = await self._llm.ainvoke(prompt)
    # ... 现有 JSON 解析 + publish_protocol_block 逻辑 ...
```

过渡语文本示例：

```python
def _build_transition_text(self, completeness: Any) -> str:
    """根据上下文生成自然的过渡语。"""
    what = getattr(completeness, "what", None) or "你的目标"
    return f"基于你提到的「{what}」，结合你的历史记录，我整理了一个建议：\n\n"
```

**效果**：用户说"我想早睡，11点前睡"，会先看到"基于你提到的「早睡」，结合你的历史记录，我整理了一个建议："这段文字流式打出，然后紧接着出现 plan_proposal 卡片。等待感大幅降低，且文本是流式的（打字机效果），JSON 部分保持一次性渲染（卡片完整出现）。

**澄清路径（clarification_request）不需要前置文本**——因为 clarification 本身就是文本 question，已经是自然的反馈。

## 4. 数据流

### 4.1 任务完成 → 记忆回写

```
用户在 PlanScene 勾选任务完成
→ PATCH /api/v1/tasks/{id} {status: "done"}
→ plan_service.update_task_status(..., container=container)
→ 任务状态变 done
→ _persist_task_memory()
  → ContentNormalizer.from_task() 生成 source=task 的 atom（importance=0.6）
  → MemoryGateway.persist_atom()
    → gate.should_persist()：content_valid ✓ + crisis ✓ + emotional_significance（importance≥0.4 兜底）✓ + dedup ✓
    → EpisodicMemory.store（importance > 0.5 阈值）✓
  → 写入 episodic_memories 表
→ 后续对话中 Agent 检索记忆时，能看到"完成了任务「早睡」"
```

### 4.2 周报生成 → 计划执行段落

```
用户点"生成本周周报"
→ weekly_service.create_weekly_report()
→ _plans_in_week() 查询本周 plan/task
→ _build_weekly_content() 组装含【本周计划执行】数据块的 content
→ ExecutionPlanner → InsightAgent.run()
  → _detect_report_type 检测到"周报"关键词 → weekly 模式
  → INSIGHT_REPORT_SYSTEM prompt（含第5段"计划执行回顾"指引）
  → ainvoke 生成整篇周报，包含 ✅ 计划执行回顾 段落
→ 写入 WeeklyReportRow
```

### 4.3 真实流式回复

```
用户发消息
→ POST /messages/stream → generate_reply_streaming（P3 重构版）
→ _prepare_reply_context()：危机检测 + 意图分类 + RAG + episodic（Stage 1-3，同步）
→ run_conversation_loop_streaming()：
  → 工具轮 invoke（非流式）
  → 最终回复 llm.astream() → StreamingSafetyGuard 三防线过滤
  → 逐 token publish TEXT_DELTA
→ 用户看到真正的打字机效果（首 token 延迟 ≈ LLM 首 token 延迟）
→ 流结束后 _maybe_persist_episodic（用聚合文本）
```

## 5. 错误处理

| 场景 | 处理 |
|------|------|
| 记忆回写失败（gate 拦截 / DB 错误） | best-effort，`_persist_task_memory` 内 try/except，warning 日志，不影响任务状态变更 |
| 周报生成时无 plan 数据 | `_plans_in_week` 返回空，`_build_weekly_content` 不追加【本周计划执行】块，prompt 指引"没有计划数据则跳过" |
| astream 不支持（LLM 无 astream 方法） | `run_conversation_loop_streaming` 已有 ainvoke 降级（第 806-809 行） |
| 流式过程 DB session 过期 | `run_conversation_loop_streaming` 内的 `session.add_turn` 在流结束后调用，期间不访问 DB；前置上下文已 commit |
| token 统计估算偏差 | docstring 明确标注"estimated"，真实 tokenizer 推迟到 P5 性能探针 |

## 6. 测试策略

### 6.1 后端单元测试

| 测试文件 | 覆盖范围 |
|---------|---------|
| `tests/unit/services/test_normalizer.py`（扩展） | `from_task` 生成正确 atom（source/mood/importance/tags） |
| `tests/unit/services/test_plan_service.py`（扩展） | `update_task_status` done/skipped 触发记忆回写；container=None 时不触发 |
| `tests/unit/services/ai/test_conversation_loop.py`（扩展） | 流式路径用真实 astream（mock LLM.astream yields tokens） |
| `tests/unit/services/test_conversation_ai_service.py`（扩展） | `generate_reply_streaming` 走真实流式路径（不再走模拟分块）；token 估算非零 |

### 6.2 集成测试

| 测试文件 | 覆盖范围 |
|---------|---------|
| `tests/e2e/test_plan_skill_flow.py`（扩展） | 任务完成 → episodic memory 多一条 source=task |
| `tests/e2e/test_weekly_plan_section.py`（新增） | 周报含计划执行段落 |
| `tests/unit/services/test_weekly_service.py`（扩展） | `_plans_in_week` 正确筛选本周 plan/task |

### 6.3 Eval 闸门

P3 合并前必须通过现有 eval 基线，确保重构不破坏生成质量。

## 7. 实施顺序

### 第一阶段：记忆闭环（约 3 天）
1. `atom.py` source 枚举扩展 + `normalizer.from_task`
2. `plan_service.update_task_status` 触发回写 + API 层传 container
3. 测试 + e2e 验证

### 第二阶段：周报段落（约 2 天）
4. `weekly_service._plans_in_week` + `_build_weekly_content` 注入
5. `INSIGHT_REPORT_SYSTEM` prompt 加段
6. 测试

### 第三阶段：真实 astream 重构（约 5-7 天）
7. 提取 `_prepare_reply_context()`（从 generate_reply 抽 220 行）
8. `generate_reply_streaming` 改用真实流式路径
9. `TracingLLMClient._record_streaming` token 估算修复
10. 全套测试 + eval 闸门

## 8. 验证清单

### 记忆闭环
- [ ] `UnifiedMemoryAtom.source` 含 "task"
- [ ] `ContentNormalizer.from_task` 生成 importance=0.6 的 atom
- [ ] `update_task_status` done 时触发记忆回写
- [ ] 回写通过四维门控（importance 兜底）
- [ ] 回写失败不阻塞任务状态变更

### 周报段落
- [ ] `weekly_service._plans_in_week` 筛选本周 plan/task
- [ ] `_build_weekly_content` 追加【本周计划执行】块
- [ ] `INSIGHT_REPORT_SYSTEM` 含第5段指引
- [ ] 无 plan 数据时周报正常生成（跳过段落）

### 真实 astream
- [ ] `_prepare_reply_context` 提取 generate_reply 的 Stage 1-3
- [ ] `generate_reply_streaming` 调用 `run_conversation_loop_streaming`
- [ ] 流式路径首 token 延迟显著低于 P0 模拟流式
- [ ] `TracingLLMClient._record_streaming` token 估算非零
- [ ] 危机短路、工具调用、记忆回写在流式路径下都正常工作
- [ ] generate_reply（非流式）不受影响

### 验证
- [ ] 所有单元测试通过
- [ ] e2e 集成测试通过
- [ ] 现有 eval 基线不退化

## 9. 风险与缓解

| 风险 | 缓解 |
|------|------|
| `_prepare_reply_context` 提取破坏 generate_reply | 提取后 generate_reply 内部改为调 `_prepare_reply_context` + 原 Stage 4-5，保持行为等价；用现有 600+ 测试做回归 |
| 流式路径 token 统计估算不准 | docstring 标注 estimated；真实 tokenizer 推迟 P5 |
| 任务回写产生大量低质记忆 | importance=0.6 + dedup 门控（24h Jaccard 0.85）；可配置开关 |
| 周报段落让 InsightAgent 分散注意力 | prompt 约束"没有计划数据则跳过"；数据块用明确分隔符 |
| DB session 在流式期间过期 | 前置上下文已 commit；流式期间不访问 DB；后置回写在新 session |
