# V3 P7: 中间件管道 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 抽取两场景真实复用的 Safety / Finalize 钩子为轻量中间件管道；同时修复场景一流式路径缺失记忆写回的缺口。可选注入，简单场景零开销跳过。

**Architecture:** `MiddlewareBase`（`on_system_prompt` / `on_reply` 两钩子）+ `MiddlewarePipeline`（有序 fold / 逐项 best-effort）+ `SafetyMiddleware`（危机准则注入，幂等）+ `FinalizeMiddleware`（统一记忆写回）。接入 `trigger_analysis_streaming`（场景一）与 `generate_reply_streaming` / `run_conversation_loop_streaming`（场景二）。

**Tech Stack:** Python 3.11+ / FastAPI / asyncio

**Spec:** `docs/superpowers/specs/2026-08-12-v3-p7-middleware.md`

---

## 文件结构

### 新建文件
| 文件 | 职责 |
|------|------|
| `server/app/shared/middleware/__init__.py` | 公共导出 + `build_default_pipeline()` |
| `server/app/shared/middleware/base.py` | `MiddlewareContext` / `MiddlewareBase` / `MiddlewarePipeline` |
| `server/app/shared/middleware/safety.py` | `SafetyMiddleware` |
| `server/app/shared/middleware/finalize.py` | `FinalizeMiddleware` |
| `server/tests/unit/shared/test_middleware.py` | 中间件单测 + 危机回归 |

### 修改文件
| 文件 | 改动 |
|------|------|
| `server/app/services/conversation_ai_service.py` | `generate_reply_streaming` 接入管道：非危机路径传管道进 loop + `run_on_reply` 替换内联 `_maybe_persist_episodic`；危机路径发完安全模板后 `run_on_reply`（审计写回） |
| `server/app/services/ai/conversation_loop.py` | `run_conversation_loop_streaming` 新增 `middleware_pipeline` 可选参数，system prompt 构建处 `apply_system_prompt` |
| `server/app/services/analysis_service.py` | `trigger_analysis_streaming` 的 `finally` 接入 Finalize 写回（补缺口） |
| `.cursor/rules/current_phase.mdc` | 指针更新：P0–P6 ✅，P7 ✅ |
| `docs/superpowers/plans/2026-08-07-v3-p0-streaming.md` 等 | 归置 P0 遗留未跟踪文档（chore commit） |

---

## Task 1: middleware 包（base + safety + finalize）

**Files:**
- Create: `server/app/shared/middleware/__init__.py`
- Create: `server/app/shared/middleware/base.py`
- Create: `server/app/shared/middleware/safety.py`
- Create: `server/app/shared/middleware/finalize.py`
- Create: `server/tests/unit/shared/test_middleware.py`

- [ ] **Step 1: 编写失败测试** `server/tests/unit/shared/test_middleware.py`
- [ ] **Step 2: 运行确认 FAIL**（`ModuleNotFoundError`）
- [ ] **Step 3: 实现 base.py**（Context / Base / Pipeline）
- [ ] **Step 4: 实现 safety.py**（`CRISIS_SYSTEM_BLOCK = EMPATHY_CRISIS_BLOCK`，幂等注入）
- [ ] **Step 5: 实现 finalize.py**（情绪门槛 + severe 审计 + 按 scenario 构建 atom + enqueue）
- [ ] **Step 6: 运行确认 PASS + ruff + mypy**
- [ ] **Step 7: 提交**

## Task 2: 场景二接入（Safety + Finalize）

**Files:**
- Modify: `server/app/services/ai/conversation_loop.py`
- Modify: `server/app/services/conversation_ai_service.py`

- [ ] **Step 1: `run_conversation_loop_streaming` 新增 `middleware_pipeline` 参数**，system prompt 构建处 `apply_system_prompt`
- [ ] **Step 2: `generate_reply_streaming` 构建 ctx + 默认管道**；非危机路径传管道进 loop；回合结束 `run_on_reply` 替换 `_maybe_persist_episodic`
- [ ] **Step 3: 危机路径**：发完安全模板后 `run_on_reply`（ctx.reply_text = safe_response，severe 审计写回）
- [ ] **Step 4: 运行现有测试确认不退化**（`test_conversation_ai_service.py` / `test_conversation_loop.py` 全绿）
- [ ] **Step 5: 新增危机回归测试**：接入管道后 crisis intent 仍单 chunk 安全模板 + REPLY_END
- [ ] **Step 6: lint + 提交**

## Task 3: 场景一接入（Finalize 补写回缺口）

**Files:**
- Modify: `server/app/services/analysis_service.py`

- [ ] **Step 1: `trigger_analysis_streaming` 的 `finally`**：`_persist_analysis_streaming` 后执行 Finalize 写回（diary scenario，`always_persist=True`）
- [ ] **Step 2: 新增回归测试**：流式完成后 `enqueue_task(persist_atom)` 被调度（patch enqueue_task）
- [ ] **Step 3: 现有 `test_analysis_service.py` / `test_analysis_memory_sync.py` 不退化**
- [ ] **Step 4: lint + 提交**

## Task 4: 全量验证 + 指针更新 + 收尾

- [ ] **Step 1: `make test`**（pytest + vitest）全绿
- [ ] **Step 2: `make lint`**（ruff + mypy + eslint + vue-tsc）通过
- [ ] **Step 3: 更新 `current_phase.mdc`**：P0–P6 ✅、P7 ✅、最后更新日期
- [ ] **Step 4: chore 提交归置 P0 遗留未跟踪文档**（`docs/superpowers/plans/2026-08-07-v3-p0-streaming.md` + spec）
- [ ] **Step 5: 分支 `feature/v3-p7-middleware` 全部提交 → PR**（描述含 标题/功能描述/实现思路/测试方式）
