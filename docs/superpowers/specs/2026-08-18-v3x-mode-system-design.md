# V3.x: 用户模式体系（日常 / 跟进 / 内视）

> **阶段**: V3.2（V3 P0–P7 已合入 main 之后的新一轮）
> **日期**: 2026-08-18
> **定位修正**: 本项目**不再是**"心理陪伴"产品。目标产品是**个人生活记录 + 规划 + 洞察复盘**工具。本设计中任何诞生于"心理陪伴"时期的旧表述均不作为依据（在代码里的残留文案另列清单，属可选清理，不在本 spec 范围内）。

## 1. 背景与本阶段目标

项目已具备完整的任务规划域：`Plan`/`Task` 数据模型、`/api/v1/plans` 与 `/api/v1/tasks` 全 CRUD、`PlannerAgent`（`plan_exploration` 意图 → 多轮澄清 + `plan_proposal` 协议块）、只读工具 `list_todos`/`get_plan_progress`。

本阶段在既有底座上补齐"**人与 Agent 对同一份个人计划的立体协作**"：
1. **计划作为知识来源**——场景二会话可把用户的活跃计划/今日待办作为常驻上下文注入。
2. **双向交互**——Agent 支持对既有计划/任务**主动提出修改**（调整、清理、补充），不再局限于"新建提案"；但**一切写库仍须用户显式确认**（维持既有"提案-确认"写路径，Agent 零写权限不变）。
3. **用户模式体系**——把"Agent 知道多少 / 语气多主动"抽象成一个**用户可见、可切换、可按日自动判基**的模式：`日常 / 跟进 / 内视`。

**核心承诺**：
- Agent **依旧零写权限**：所有增/改/删仍通过前端确认后调 REST 落库。本阶段把"提案"从新建扩展到"修改既有计划/任务"，但不放开自主写库。
- **保持克制**：自动切换每天至多 2 次（当日首次会话定基调 1 次 + 会话中情绪跌破阈值切内视 1 次）；手动切换不受限。
- **不施压**：任何模式下都禁止"必须/赶紧/逾期警示/追责过往"类文本——这是全局底线，不是某一档的特权。
- **判境与表现分离**：`MoodMonitor`（服务层判据）与 `ModePromptBuilder`（中间件文案）互不了解对方实现。

## 2. 三档模式总览

| 档 | 内部 mode | 触发（自动） | 知情度 | 主动性/语气 | 说明（用户可见） |
|----|-----------|-------------|--------|------------|----------------|
| 日常 | `daily` | 当日首次会话默认基调 | 注入计划知识 | 协助记录/规划/复盘，推进但不催 | 帮你记录、规划、复盘，推进但不催促 |
| 跟进 | `followup` | ①用户手动 ②系统判：情绪平稳 + 有计划未完成张力 | 注入计划知识 | 用户愿意时温和带一两步，不勉强 | 你愿意时，带你往前带一两步，不勉强 |
| 内视 | `introspection` | ①用户手动 ②会话中 C 判据情绪跌破阈值 ③昨日内视延续 | 可收起计划 | 暂缓计划推进，先回应此时的状态与卡点 | 今天先从内里看看此刻的自己，暂缓计划推进 |

**内部约束**：
- 三档共用**一份"计划知识"**，由当前档决定如何注入（注入 / 弱化 / 收起）。
- 任何档都不允许施压措辞（全局底线，复用並向完整 prompt 推广 PlannerAgent 已有禁则）。

## 3. 判境模块

### 3.1 数据——新增表 `daily_modes`

轻量权威读写点，作为"每日判境"与"洞察/复盘"的素材。

```python
class DailyModeRow(Base):
    __tablename__ = "daily_modes"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    date: Mapped[date] = mapped_column(index=True)
    baseline_mode: Mapped[str] = mapped_column(String(20))  # daily/followup/introspection
    auto_switched: Mapped[bool] = mapped_column(default=False)   # 当日是否已消耗"自动切换1次"
    switch_count: Mapped[int] = mapped_column(default=0)
    mood_signals_json: Mapped[str] = mapped_column(Text, default="{}")  # {"trend":..., "score":...}
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)
    UniqueConstraint(user_id, date)
```

- Alembic 迁移 `008_daily_modes.py`。
- 不使用新增大表；`mood_score`/`daily_digests`/`long_term_memory` 均为既有来源。

### 3.2 判据权重

| 判据 | 权重 | 数据来源 |
|------|------|---------|
| A 当日/近期情绪 | 20% | `mood_score` + 近 7 天趋势 |
| B 计划张力 | 20% | 今日到期待办 + 未完成状态 |
| C 当轮实时情绪 | 60% | 复用意图/情感通道（主判据），后台增强（可选） |

权重作为**规则分层信号**，非模型可调参数；落成确定性的分层判定（见 §3.3/§3.4），不引入 LLM 加权计算。

### 3.3 每日基调判定（B1）——首次会话触发，产出 `baseline_mode`

点查早退，不叠加：
1. 昨日 `introspection` 且今晨 A 趋势仍偏弱 → `introspection`（延续）。
2. A 判据（当日已写 `mood_score` + 趋势均值）明显偏低 → `introspection`。
3. B 判据（今日到期待办未完成）且 A 情绪不差 → `followup`。
4. 否则 / 无信号 → `daily`（默认，不激进）。

### 3.4 会话中实时监听（B2）——C 判据，当日第 2 次（至多）

- 复用意念/情感通道（a）与主 LLM 寄生病灶（b）作为**零新增阻塞调用**的主判据。
- 可选的旁路情感 LLM（c）仅作**后台并行增强**，其结果**下一轮**才生效，不阻塞当前流式回复，不影响本轮感知延迟。
- 触发：当轮情绪分跌破阈值 → 本轮结束后应用 `mode=introspection`，本档内不发 `mode_switch` 状态的中间改写（避免撕裂）。
- **内视锁存**：一旦自动进入 `introspection`，当日不再自动转回（防抖，符合"当天受了不催"）；只能用户手动离开。
- 一日内自动切换合计 ≤ 2 次。

### 3.5 手动覆盖（B3）

- 手动切换不计入每日自动上限，随时可用，立即生效并写 `daily_modes`（`auto_switched` 不变）。

### 3.6 阈值/常量集中配置

判定阈值、近期天数等集中在 `MODE_RULES`（config，非硬编码进代码），便于调参。例：
- `live_emotion_threshold`（C 阈值）
- `trend_window_days`（近 7 天）
- `followup_needs_pending_task`（B 判定开关）
- `enable_live_emotion_enhancement`（c 增强通道开关，**运行侧开关非 prompt 词**；Agent 不感知 C 的存在）

## 4. 表现层

### 4.1 两层分离抽象

- **判境层** `MoodMonitor`（服务层，纯判据）：读 signals → 出"当前档位"。可单测、纯函数化。
- **表现层** `ModePromptBuilder`（中间件，纯文案）：读"当前档位"+ `profile_style` → 拼 `【当前计划与状态】` + `【模式语气】` 两块注入 system prompt。可采用 / 符合 P7 Middleware 抽象。

C 是否启用是**判境层的确定性策略/配置**，**绝不写入 system prompt、模型完全不感知**。

### 4.2 知识来源注入（C1）

- 常态/跟进：注入 `【当前计划与状态】`（活跃计划标题 + 今日待办 + 进度汇总 + 心情趋势一句），上限约 300 字符。
- 内视：改为 `【当前计划与状态】【本档暂缓重启计划推进】`，弱化/省略计划内容。

### 4.3 三档语气模板（C2）

| 档 | 注入的语气指令（示例） |
|----|----------------------|
| `daily` | 并列生活助手，协助记录/规划/复盘。已知悉计划与待办，可自然协助推进，但不得催促、不放大逾期、不用"必须/赶紧"。用户未要求不反复提醒。 |
| `followup` | 在 `daily` 基础上追加：当用户尝试推进或被计划卡住时，可温和提一句可执行的下一步。频率克制、一句话点到为止、不追责过往未完成。 |
| `introspection` | 此刻先放下计划推进，专注回应用户当下的状态与被卡住处。可暂不提待办与截止。语气平缓，不问"什么时候能做"。 |

**全局硬底线**：任何档绝不用施压措辞（"必须/赶紧/逾期警示/追责"），向完整 system prompt 推广。

## 5. 前端与协议

### 5.1 事件 `mode_state`（自审后收敛）

丢弃初版繁琐的 `mode_switch` 元数据堆叠（`trigger/by/once` 等）。前端仅需两件事：当前档 + 是否提示。因此定为一支**轻量快照**事件：

```json
{
  "type": "protocol_block",
  "block": {
    "block_type": "mode_state",
    "block_id": "ms-<daily-or-uuid>",
    "data": {
      "mode": "introspection",              // 当前最终档
      "display_name": "内视",
      "light_notice": true               // 是否需要给用户一条轻提示，合并去重
    }
  }
}
```

- 状态变更**合并为快照**广播（不逐次广播多段），避免档位闪烁竞态。
- `light_notice` 仅在 `自动` 进入某档**且首次**时为 true；此后同档不再提示（防唠叨）。
- 手动切换时 `light_notice=false`（用户自知）。

### 5.2 前端组件

- **模式徽标**：会话顶栏一处可显示当前档名（`日常 / 跟进 / 内视`），hover 显示那句话说明。
- **模式切换（手动覆盖）**：点徽标弹三档，手动切换立即生效（不计自动配额），并写明"选它会怎样"。
- **自动轻提示**：`light_notice=true` 时给一条温和 toast（如"感觉你有些累，我们从当下说起"），不改用户覆盖；徽标随之更新。
- **可隐藏**：提供一个入口让用户隐藏徽标（避免"时刻被感知"的负担）。
- **洞察/复盘联动**：`daily_modes` 落库后，复盘页可展示"这一周你主要处于哪一档"作为洞察素材（符合产品"洞察复盘"定位；本期 MVP 只落库，页面可视化列为后续项）。

### 5.3 完整数据流

```
① 当日首次会话
   → MoodMonitor 读 daily_modes + signals → 定 baseline（daily/followup/introspection）
   → 写 daily_modes → ModePromptBuilder 拼【计划+语气】→ 流式回复（首条含 mode_state）
② 会话中
   → 每轮宿主判据 a+b（复用意图/寄生情绪）
   → C 若跌破阈值 → 异步落地 → 结束后发 mode_state(introspection, light_notice=true)
   → 次日延续：昨日 introspection 且今晨偏弱 → 保持 introspection
③ 用户手动
   → 点徽标切档 → 立即生效 → 写 daily_modes(manual) → 后续轮次 prompt 更新（light_notice=false）
```

### 5.4 自审修正清单（第四节初版已修正项）

- 丢弃 `trigger/by/once` 元数据 → 收敛为 `mode_state` 快照。
- 增加"计划状态过期"的刷新时机（会话内待办变化后重拉一次计划注入）。
- 自动轻提示只发一次（去重），避免唠叨。
- 徽标可隐藏入口。
- 避免多段广播导致的档位闪烁：统一快照合并。

## 6. 错误处理

| 场景 | 处理 |
|------|------|
| `MoodMonitor` 读不到 `daily_modes`（首日） | 按默认 `daily` + 无信号处理，兜底不激进 |
| 会话中计划状态变更导致注入过期 | 下次注入时重拉"当前计划与状态"，保证新鲜 |
| 判据源故障 / 降级 | 回退默认 `daily`，记录降级日志，不影响主回复链路 |
| `mode_state` 广播失败 | 忽略（前端下次轮次熵补），不阻塞回复 |
| 多次自动切换竞争 | 合并快照 + 当日 switchCount 上限拦截 |

## 7. 测试策略

### 7.1 单元（后端）
- `test_mood_monitor.py`：A/B/C 分层、昨日延续、阈值越界、内视锁存、手动不计配额、默认兜底。
- `test_mode_prompt_builder.py`：三档文案正确、`【当前计划与状态】`是否/如何注入、无施压措辞断言。
- `test_daily_modes.py`：ORM、唯一约束、upsert。

### 7.2 协议 / 前端
- `mode_state` schema + `light_notice` 去重。
- 徽标显示/隐藏、手动切换即时生效、自动轻提示一次去重。
- daily_modes 关联渲染。

### 7.3 e2e
- 完整链路过一遍：手动切档 → 当日首次会话定基调 → 情绪跌破切成内视 → 监控闭环。
- 计划知识注入在"日常/跟进"出现、在内视弱点/省略。

### 7.4 eval 闸门
- 不破坏现有 plan / generation 基线（RAG 容差 0.05 + generation judge）。
- 讲"任何档无施压措辞"加入生成 rubric 的一条硬判据。

## 8. 范围边界

### 包含
- `daily_modes` 表 + 迁移；`MoodMonitor` 判境；`ModePromptBuilder` 中间件；`mode_state` 协议 + 前端徽标/手动切换/一次性轻提示；计划注入。
- Agent 侧"修改既有计划/任务提案"能力扩展（从新建扩展到调整/清理，仍提案-确认）。

### 不包含（留后续）
- 主动写库/自主增删（维持 Agent 零写权限）。
- `daily_modes` 可视化的洞察报告页面（本期只落库）。
- 提醒推送 / 日历集成 / 习惯追踪。
- 遗留"心理陪伴"prompt 文案的系统性清理（可选、非本 spec 范围）。

## 9. 实施顺序

1. `MODE_RULES` 配置 + `daily_modes` 迁移 + ORM。
2. `MoodMonitor` 判境模块（含单元测试）。
3. `ModePromptBuilder` 中间件接入 ConversationLoop prompt。
4. `mode_state` 事件 + 前端徽标 / 手动切换 / 轻提示。
5. Agent 侧"修改既有计划"提案扩展。
6. e2e + eval 闸门回归。
