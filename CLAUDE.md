# Night Diary V2

本地桌面应用。Tauri v2 + Vue 3 + Python FastAPI sidecar，SQLite + ChromaDB，无 Docker/Redis/JWT。

## Git 规范

- **永远不直接 push main**，所有改动走 PR
- 从 main 开新分支前：`git checkout main && git pull`
- 分支命名：`feature/` / `fix/` / `refactor/` / `chore/` / `docs/`
- 提交用约定式提交：`feat:` `fix:` `chore:` `docs:` `test:` `refactor:` 等
- 提交时不要跳过 hook（不用 `--no-verify`）
- **不 amend 已推送的提交**；pre-commit hook 失败后修复并新建 commit，不 amend
- 每次提交附带：`Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>`

### 提交粒度铁律（所有 Phase 强制执行）

**核心原则：实现与测试配对提交。每个 PR 2-8 个 commit，每个 commit ≤ 500 行、只做一件事。**

| 禁止 | 原因 |
|------|------|
| 单 commit 堆 5+ 不相关改动 | reviewer 无法定位问题；B-1 的错误（799 行/1 commit）不复现 |
| 实现和测试分两个 commit | 中间状态无验证；CI 不红但实际可能坏 |
| 逐文件提交（types.py → store.py → ...） | 过度拆分，每个 commit 不完整 |

**每个 commit 的可验证性标准**：
- 该 commit 如果有对应的测试文件，测试必须通过
- 纯依赖/配置/文档 commit 不需要测试
- `git log --oneline` 应能看出每个 commit 做了什么

### Phase B commit 模板（Python 后端领域模块）

```
commit 1: chore(server): add [依赖名] deps / config
commit 2: feat(domain): add [模块名] types and scaffold with tests
commit 3: feat(domain): implement [核心类 A] with tests
commit 4: feat(domain): implement [核心类 B] with tests
commit 5: docs: sync task.md Phase B-[N] checkboxes
```

B-1 对应示例（4 commit）：chore(pyproject) → feat(types+store) → feat(extractor) → docs(task.md)

### Phase C commit 模板（服务层 + API 路由）

```
# 服务层（C-1 最重，7-8 commit）:
commit 1: chore(server): add service-layer deps
commit 2: feat(services): add diary_service with tests
commit 3: feat(services): add analysis_service with tests
commit 4: feat(services): add ai/router.py + ai/prompts.py with tests
commit 5: feat(services): add ai/executors (chain/agent/multi_agent) with tests
commit 6: feat(services): add feedback_service, tag_service, model_service with tests
commit 7: docs: sync task.md C-1 checkboxes

# API 路由（C-2, 4 commit）:
commit 1: feat(api): add AppError base class + error handlers with tests
commit 2: feat(api): add diary + analysis routes with tests
commit 3: feat(api): add feedback, tags, models, stats routes with tests
commit 4: docs: sync task.md C-2 checkboxes

# LLM 管理（C-3, 4 commit）:
commit 1: feat(shared): add Fernet encryption/decryption with tests
commit 2: feat(shared): add LLMFactory with per-tier model selection and tests
commit 3: feat(services): update model_service to use encryption + tier config
commit 4: docs: sync task.md C-3 checkboxes
```

### Phase D commit 模板（Vue 前端）

前端组件的「测试」含 vitest 单元测试 + 手动视觉验证。vitest 必须与组件同 commit。

```
# 设计系统（D-1, 6 commit）:
commit 1: chore(frontend): install GSAP dependency
commit 2: feat(ui): add CSS base + theme variables (base.css, day.css, night.css)
commit 3: feat(ui): add GlassPanel, GameButton, PageTransition with tests
commit 4: feat(ui): add ParticleBackground, AITypingIndicator, MoodSelector, CustomTitlebar with tests
commit 5: feat(ui): add animation CSS (transitions, particles, glow)
commit 6: docs: sync task.md D-1 checkboxes

# 通用模式（D-2/D-3/D-4）:
commit 1: feat(frontend): add API module + Pinia store with tests
commit 2: feat(frontend): add [feature] components with tests
commit 3: feat(frontend): add [scene] page + Vue Router config
commit 4: docs: sync task.md D-[N] checkboxes
```

### Phase E commit 模板（交付）

E 阶段无传统「实现+测试」配对，按「逻辑完整性」判定原子化——每个 commit 是一个完整的交付步骤。

```
commit 1: chore(build): finalize PyInstaller spec with all hidden imports
commit 2: chore(build): configure Tauri bundle (NSIS installer, embed Python exe)
commit 3: feat(build): add model downloader with progress UI
commit 4: feat(build): add auto-backup on app exit (Rust side)
commit 5: test(e2e): add Playwright E2E test (diary CRUD → AI analysis → feedback)
commit 6: docs: finalize README, user-guide.md, dev-guide.md
commit 7: chore: sync task.md E-1 checkboxes
```

## PR 规范

- 完成后创建 PR（`gh pr create` 或 GitHub Web）
- PR 标题 ≤70 字符，说明做了什么
- PR 描述必须含三段：**功能描述** → **实现思路** → **测试方式**
- 大型 PR（对应 task.md 完整章节）使用：Overview / Tasks / Verification
- 合并前确认 CI 全绿 + `main` 可运行

## 常用命令

```bash
make dev-api      # Python 后端 → 127.0.0.1:8000
make dev-web      # Tauri 桌面应用（npm run tauri dev）
make test         # pytest + vitest
make lint         # ruff + mypy + eslint + vue-tsc
```

## AI 工程质量标准

本项目核心是 Multi-Agent 系统。以下标准与 Git/PR 规范同等重要。

### 可观测性

每次 LLM 调用必须可追溯，存储于本地 SQLite，不上传外部服务：

| 记录类型 | 存储表 | 关键字段 |
|----------|--------|----------|
| LLM 调用 | `llm_call_logs` | agent_name, call_type, prompt, response, latency_ms, tokens_in/out, model, tier |
| Agent 决策 | `agent_decisions` | agent_name, decision_type, input_summary, output, reason |

- Agent 通过 DI 接收 `LLMCallTracer`，与 LLM、DB session 同级
- 写入异步完成，不阻塞 Agent 主流程

### 测试理念

- **单元测试 mock LLM**：验证 Agent 控制流（路由、fan-out、合成）
- **Eval 测试真实 LLM**：`server/tests/eval/` 下 10-20 条固定日记输入 + 结构化评判标准，prompt 改动后手动跑 `make eval`
- **统计测试**：Thompson Sampling 跑 N≥1000 验证 Beta 分布，不依赖单次断言
- **级联失败测试**：RetrievalAgent 多跳检索的漂移场景、Worker 超时降级

### 降级与韧性

- LLM API 不可达：返回预设安全模板，不白屏或抛异常
- Crisis 检测命中：短路到安全模板，不送 LLM
- 每个 Agent 独立超时：Supervisor 最长，Worker 较短
- Supervisor 容忍部分 Worker 失败：如 Retrieval 挂了，用剩余 Worker 结果降级合成

## 当前状态

✅ Phase A 完成（5/5 PR 已合并）。▶ Phase B 进行中：B-1 已合并，下一步 B-2（`feature/rag-foundation`）。

全项目 commit 预算：~80 commits / 17 PRs ≈ 4.7 commits/PR。

规则文件在 `.cursor/rules/`（本地 Agent 辅助），`task.md` 是施工蓝图，`CLAUDE.md` 是跨会话的规范真相源。
