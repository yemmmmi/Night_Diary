# Night Diary V2

本地桌面应用。Tauri v2 + Vue 3 + Python FastAPI sidecar，SQLite + ChromaDB，无 Docker/Redis/JWT。

## Git 规范

- **永远不直接 push main**，所有改动走 PR
- 从 main 开新分支前：`git checkout main && git pull`
- 分支命名：`feature/` / `fix/` / `refactor/` / `chore/` / `docs/`
- 提交用约定式提交：`feat:` `fix:` `chore:` `docs:` 等，原子化
- 提交时不要跳过 hook（不用 `--no-verify`）
- **不 amend 已推送的提交**；pre-commit hook 失败后修复并新建 commit，不 amend
- 每次提交附带：`Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>`

## PR 规范

- 完成后创建 PR，用 `gh pr create`；描述含 Summary + Test plan
- PR 标题 ≤70 字符，说明做了什么
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

Phase A（新地基）进行中。已完成 PR #3–#7。下一步：phase-a-4 构建收尾 → phase-a-5 PyInstaller sidecar 打包。

规则文件在 `.cursor/rules/`（Cursor 使用），`task.md` 是施工蓝图。
