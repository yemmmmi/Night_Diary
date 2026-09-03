# PR9 实施计划 — digest 生产统一：纯文本日记接入每日摘要

> 分支 `feat/digest-unify-pr9`（基于 main @ PR8 merge）。纯后端 PR，前端零改动。

## 背景

digest（每日结构化摘要，`daily_digests` 表）是笔谈附日记上下文注入与记忆同步的核心数据。当前生产路径不对称：

| 来源                   | digest 现状                                                            |
| -------------------- | -------------------------------------------------------------------- |
| 卡片日记（记一笔）            | ✅ 已接入：`card_service` 增删改 → `refresh_cards_section` 零 LLM 重聚合 cards 段 |
| 卡片展开日记               | ✅ 已接入：`expand_to_diary` → `trigger_analysis` → LLM 提取 diary 段        |
| **手写纯文本日记**          | ❌ **不产 digest**（`create_entry`/`update_entry` 无任何触发）                 |
| **记录 skill 日记**（PR8） | ❌ **不产 digest**（同样走 `create_entry`）                                  |

后果：用户手写/口述的日记，笔谈引用时只能全文回退（token 成本高、语义稀），情景记忆同步也缺位（违反项目硬约束「日记分析必须写情景记忆并触发长期画像晋升」）。

## 目标

1. 纯文本日记（手写 + 记录 skill）创建/编辑/删除后，当天 digest 自动重建。
2. digest 的 diary 段语义统一为「**当天全部纯文本日记条目的聚合提取**」，消除现存的 last-writer-wins 隐患（同日多篇日记时只反映最后一篇触发分析的内容）。
3. 顺带补齐纯文本日记的情景记忆同步（硬约束要求）。
4. 消费端零改动：笔谈 `_day_digest_block` 与记忆同步已有「无 digest → 全文回退」，生产端补齐后自动受益。

## 架构决策

- **D1 新建 day-level worker，不复用** **`trigger_analysis`**：trigger\_analysis 是 per-diary 语义（AnalysisRow 落库 + `entry.reply` 短回复写入 + trace），纯文本日记不需要产出树洞短回复。新 worker 只管 digest。卡片展开路径**暂不改动**——同日若再有纯文本日记触发，聚合提取会覆盖 diary 段，最终一致；v3 删除树洞 reply 时再将其收编。

- **D2 提取核心复用** **`treehole.run_treehole`，忽略 reply**：单次 LLM 调用产 reply+digest，prompt 不动、提取质量零回归。不拆新 `extract_digest()`（拆 prompt 有质量回归风险，留到 v3 删 reply 时一并做）。保留 `detect_crisis` 短路 → `fallback_treehole`（安全约束）。

- **D3 触发点放** **`diary_service`（lazy import），签名加** **`container`** **可选参**：

  - `create_entry` / `update_entry` / `delete_entry` 增加 `container: ServiceContainer | None = None`（先例：`collection_manager` 参数）。

  - service 内 lazy import worker 的 schedule 函数，`container=None` 时静默跳过（测试与降级友好）。

  - 好处：API 路由、记录 skill、未来任何调用方自动获得触发，不会漏。循环依赖检查：worker 只 import models + treehole + digest\_service + task\_queue，不 import diary\_service → 无环。

- **D4 异步执行走** **`enqueue_task`**（RQ 优先，线程兜底——项目既有基础设施）：

  - worker 入口用 dotted path `"app.services.digest_worker.run_day_digest_refresh"`，参数 `(user_id: str, day: str, diary_id: int)` 全部可 pickle。

  - worker 内部自建会话（`SessionLocal`）与 LLM（从容器工厂取，不要求请求上下文）；实现时确认容器获取方式（`get_container` 单例或直接构建 LLMClient）。

  - 保存路径不等待提取：写日记的延迟不变。

- **D5 幂等与合并**：

  - diary 段 = 聚合当天全部条目（按 `created_at` 排序拼接，`---` 分隔）→ 重复触发结果一致，天然幂等。

  - cards 段照抄现有 digest（不重算、不动 LLM）；无现有 digest 时用 `refresh_cards_section` 语义聚合。

  - 进程内 in-flight 去重：同 `(user_id, day)` 正在跑则跳过新触发（连续写两篇日记只提取一次，取后者聚合内容时已包含前者）。

  - 删除日记后触发重建：当天已无纯文本日记时 diary 段清空、source 降为 `card`/`rule`。

- **D6 记忆同步补齐**：worker 完成提取后对**触发源 entry** dispatch `_sync_diary_to_memory(entry, reply="", container, digest)`（`from_diary` 的 `reply` 默认空串，无树洞短回复不影响 atom 结构）。per-diary 原子性保持，满足硬约束。

- **D7 LLM 不可用降级**：`run_treehole` 内部已降级 `fallback_treehole`（规则提取），worker 无需额外处理；LLM 层面完全失败时 digest 至少有规则版（情绪词计数/意图猜测），读取端不受影响。

## 任务分解

### 后端

- [ ] T1 `app/services/digest_worker.py`：`run_day_digest_refresh(user_id, day, diary_id)` worker
  - 自建 session；聚合当天 entries（`DiaryEntryRow` 按 user\_id+date 查询）+ 现有 digest cards 段

  - 无 entries → 清空 diary 段；有 → 拼接内容调 `run_treehole`（crisis 短路 / LLM None 走 `fallback_treehole`）

  - `upsert_digest` 合并（cards 段保留）+ `_sync_diary_to_memory` dispatch

- [ ] T2 `schedule_day_digest_refresh(user_id, day, diary_id, container)` 调度函数：in-flight 去重 dict + `enqueue_task` dotted path

- [ ] T3 接线：`diary_service.create_entry` / `update_entry` / `delete_entry` 加 `container` 参数并调度（lazy import）；`v1/diary.py` 路由传 container；`record_skill` 加 `container` 参数（`user_skill_service` 传入）

- [ ] T4 测试（pytest，预计 \~18 用例）：
  - worker：聚合多条目 / 单条目 / 无条目清空 / cards 段保留 / LLM 失败降级 / crisis 短路 / 记忆 dispatch 被调用

  - 调度：create/update/delete 触发（mock enqueue）/ container=None 跳过 / in-flight 去重

  - record\_skill 传 container 后触发

  - 回归：现有 992 用例不动绿

### 收尾

- [ ] T5 全量回归：**pytest 全量 + ruff（在 server 目录跑，PR8 CI 教训）+ mypy**

- [ ] T6 浏览器验证：手写日记保存 → 数秒后 digest 落库（SQL 查 `daily_digests`）；记录 skill 口述 → 同样落库；笔谈附该日记 → trace 中看到结构化 digest 块而非全文

- [ ] T7 提交（分 commit：worker / 接线 / 测试 / 计划文档）+ 推送 + PR

## 风险与对策

- **RQ worker 进程的容器获取**：若 `get_container` 不可 import，退化为直接构建（SessionLocal + LLMClient 工厂函数）；线程 fallback 模式无此问题（同进程）。T1 实现时首先确认。

- **LLM 成本**：每篇纯文本日记 +1 次 light LLM 调用（与卡片展开路径同量级）；in-flight 去重 + 幂等聚合控制重复。

- **同日多源竞争**：卡片展开（trigger\_analysis 写 digest）与 worker 并发写同一天 → 后写者胜且均为完整语义（cards+diary），无半写状态；`upsert_digest` 单行单事务。

- **旧数据**：存量手写日记无 digest——读取端已有全文回退；不回填（可后续按需跑批）。

