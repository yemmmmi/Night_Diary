# V3 P7: 中间件管道（Middleware Pipeline）规格

> **阶段定位**：P0–P6 后的可选后置阶段。设计基准见
> `docs/reports/night-diary-v3-agent-analysis/night-diary-v3-agent-analysis.html` 4.2.2 / 4.3。
> 核心原则：**先只抽 Safety / Finalize 两个有真实复用需求的钩子；全量 MiddlewareBase
> 视落地情况再决策；中间件可选注入，简单场景跳过（防过度设计）**。

---

## 1. 决策依据（P0–P6 落地后复盘）

### 1.1 两处真实重复 / 缺口

| # | 现象 | 证据 | 结论 |
|---|------|------|------|
| 1 | **记忆写回逻辑近似重复**：场景一 `_sync_diary_to_memory` 与场景二 `_maybe_persist_episodic` 都是「内容 → `ContentNormalizer` → `UnifiedMemoryAtom` → `enqueue_task(persist_atom)`」的 fire-and-forget 写回，仅 source 与归一化入口不同 | `analysis_service.py` / `conversation_ai_service.py` | 收敛为 `FinalizeMiddleware.on_reply`，单一实现 |
| 2 | **场景一流式路径缺失记忆写回**：`trigger_analysis_streaming` 的 `finally` 只做 `_persist_analysis_streaming`（AnalysisRow），从不调用 `_sync_diary_to_memory`；非流式路径（`create_analysis`/`update_analysis`）却会写 | `analysis_service.py` L656-739 对比 L96-164 | 接入 `FinalizeMiddleware` 后补上缺口（行为修复，非纯重构） |
| 3 | **危机响应指令两场景不一致**：场景一 empathy prompt 有 `EMPATHY_CRISIS_BLOCK`；场景二 `CHAT_SYSTEM_PROMPT` 完全没有危机段（只靠 Stage 2 短路 + 滑窗兜底） | `domain/agents/prompts.py` L94 / `services/ai/prompts.py` L27 | `SafetyMiddleware.on_system_prompt` 统一注入，单一来源 |

### 1.2 不做的部分（防过度设计）

- 不实现 Identity / Context / Protocol 三个中间件——P0–P6 落地后未发现同等强度的复用需求；
  待未来出现第三个消费方再补（中间件为兄弟模块，扩展成本低）。
- 不改造非流式路径（`create_analysis` / `generate_reply` 同步版）：保持既有行为，最小回归面；
  后续若同步路径也迁移，可把遗留函数折叠到中间件上。
- 场景一的 prompt 注入点位于 graph 内部（`MultiAgentGraph` 各 agent 自行拼 prompt），
  外层编排拿不到 system prompt，因此 `SafetyMiddleware` 只接入场景二；
  场景一危机段继续由 `EMPATHY_CRISIS_BLOCK`（现已成为安全块的单一来源）覆盖。
- 管道为**可选注入**：默认 `build_default_pipeline()` = Safety + Finalize；显式传空管道 =
  零开销跳过（满足「简单场景跳过」）。

---

## 2. 架构

```
server/app/shared/middleware/
├── __init__.py      # 公共导出 + build_default_pipeline()
├── base.py          # MiddlewareContext / MiddlewareBase / MiddlewarePipeline
├── safety.py        # SafetyMiddleware（on_system_prompt：危机准则注入，幂等）
└── finalize.py      # FinalizeMiddleware（on_reply：fire-and-forget 记忆写回）
```

### 2.1 MiddlewareContext

每次运行一个实例，贯穿两场景编排入口：

```python
@dataclass(slots=True)
class MiddlewareContext:
    scenario: str                 # "diary_reply" | "conversation"
    user_id: str = "default"
    content: str = ""             # 日记原文 / 用户消息
    intent: str = ""
    trace_id: str = ""
    conversation_id: str | None = None
    diary_id: str | None = None
    reply_text: str = ""          # on_reply 时填充（安全模板 / 最终回复）
    container: Any | None = None  # ServiceContainer（lazy import，避免环）
    always_persist: bool = False  # 场景一 true：日记写回不过情绪门槛
    extra: dict[str, Any] = field(default_factory=dict)  # 场景特定数据（如 entry row）
```

### 2.2 MiddlewareBase

```python
class MiddlewareBase(ABC):
    name: str = "base"
    def on_system_prompt(self, prompt: str, ctx: MiddlewareContext) -> str:
        """返回（可能被改写后的）系统提示。默认原样返回。"""
        return prompt
    def on_reply(self, ctx: MiddlewareContext) -> None:
        """回合收尾副作用。默认 no-op。实现必须吞掉自身异常（best-effort）。"""
```

### 2.3 MiddlewarePipeline

```python
class MiddlewarePipeline:
    def __init__(self, middlewares: Iterable[MiddlewareBase] | None = None): ...
    def add(self, mw: MiddlewareBase) -> MiddlewarePipeline: ...   # 链式
    @property
    def is_empty(self) -> bool: ...                                 # 空管道 → 调用方直接跳过
    def apply_system_prompt(self, prompt: str, ctx: MiddlewareContext) -> str:
        """按注册顺序 fold。"""
    def run_on_reply(self, ctx: MiddlewareContext) -> None:
        """逐个执行 on_reply；单个中间件异常吞掉记日志，不中断后续。"""
```

工厂：`build_default_pipeline() -> MiddlewarePipeline`（Safety + Finalize）。
测试/简单场景：`MiddlewarePipeline()` 空管道 = 零开销。

### 2.4 SafetyMiddleware

- `name = "safety"`
- 常量 `CRISIS_SYSTEM_BLOCK = EMPATHY_CRISIS_BLOCK`（**单一来源**：场景一继续引用原常量，
  场景二经中间件注入同一文本，两场景危机准则永不漂移）。
- `on_system_prompt`：若 prompt 已含 `## ⚠️ 危机响应模式` 标记则原样返回（幂等），否则追加。

### 2.5 FinalizeMiddleware

- `name = "finalize"`
- `on_reply(ctx)`：
  1. `ctx.container is None` 或 `ctx.reply_text` 为空 → 跳过。
  2. 情绪门槛：`abs(score) < 0.3` 且无 severe signal，且 `not ctx.always_persist` → 跳过。
  3. `MemoryGateway.from_container(container)`；`gw._episodic is None`（降级）→ 跳过。
  4. 按 `ctx.scenario` 构建原子：
     - `diary_reply`：`ContentNormalizer.from_diary(ctx.extra["entry"], reply=ctx.reply_text, user_id=ctx.user_id)`
     - `conversation`：`ContentNormalizer.from_conversation(ctx.content, reply_text=..., conversation_id=..., user_id=..., emotion_label=..., emotion_score=score)`
  5. `enqueue_task(gw.persist_atom, atom)`（fire-and-forget，与既有写回语义一致）。
  6. 全程 `try/except` 吞异常记 warning（记忆为 best-effort，失败不影响主流程）。

---

## 3. 接入点

| 场景 | 入口 | 中间件 | 位置 |
|------|------|--------|------|
| 场景一（日记→回信） | `trigger_analysis_streaming`（`analysis_service.py`） | Finalize | `finally` 块内，`_persist_analysis_streaming` 之后；补齐缺失的记忆写回 |
| 场景二（对话） | `generate_reply_streaming`（`conversation_ai_service.py`） | Safety + Finalize | 非危机路径：管道传入 `run_conversation_loop_streaming` 做 system prompt 注入；回合结束后 `run_on_reply` 替换内联 `_maybe_persist_episodic`。危机路径：安全模板发出后同样 `run_on_reply`（severe signal 审计写回，与 `_maybe_persist_episodic` 语义一致） |

`run_conversation_loop_streaming` 新增可选参数 `middleware_pipeline: MiddlewarePipeline | None = None`，
仅在 system prompt 构建处调用 `apply_system_prompt`；`None`/空管道行为与现状完全一致。

---

## 4. 验收标准

1. **单测（mock LLM）**：
   - Pipeline：空管道跳过、注册顺序、`on_reply` 单中间件异常不中断后续。
   - Safety：注入幂等；含标记的 prompt 不被二次追加。
   - Finalize：情绪门槛（<0.3 且非 severe 不写）、`always_persist`（场景一必写）、
     severe signal 必写（审计）、降级（`_episodic is None`）跳过、异常吞掉。
   - 场景一写回缺口回归：`trigger_analysis_streaming` 完成后 `enqueue_task(persist_atom)` 被调度。
2. **危机安全回归**：接入中间件后，crisis intent 仍 100% 走安全模板短路（不送 LLM），
   事件序列 REPLY_START → TEXT_DELTA → TEXT_END → REPLY_END 不变（单 chunk）。
3. **无行为退化**：`make test`（pytest + vitest）全绿；`make lint`（ruff + mypy + eslint + vue-tsc）通过。
4. `current_phase.mdc` 指针更新：P0–P6 ✅，P7 ✅。

---

## 5. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 中间件引入回归（crisis 短路被绕过） | 危机回归测试 + `run_on_reply` 吞异常；非流式路径不动 |
| 场景一写回补缺口改变行为 | 属 P7 明确修复项，测试覆盖；enqueue 仍 fire-and-forget |
| 过度设计 | 仅 2 个中间件 + 空管道零开销；未实现的 3 个中间件留待真实消费方 |
