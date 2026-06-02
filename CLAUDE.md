# Night Diary V2

本地桌面应用。Tauri v2 + Vue 3 + Python FastAPI sidecar，SQLite + ChromaDB，无 Docker/Redis/JWT。

## 入口文档

| 用途 | 文件 |
|------|------|
| 施工蓝图（所有 task 和 PR 定义） | `task.md` |
| 架构方案（为什么这样设计） | `docs/本地化桌面端重构方案.md` |
| 当前进度（下一个 PR 是什么） | `.cursor/rules/current_phase.mdc` |
| 编码规范（分层、DI、错误处理） | `.cursor/rules/coding-standards.mdc` |
| 协作规范（分支、commit 模板、PR 流程） | `.cursor/rules/collaboration.mdc` |
| V1 迁移参考 | `.cursor/rules/v1-migration.mdc` |

## Git 规范

- **永远不直接 push main**，所有改动走 PR
- 分支命名：`feature/` / `fix/` / `refactor/` / `chore/` / `docs/`
- 提交用约定式提交：`feat:` `fix:` `chore:` `docs:` `test:` `refactor:`
- 每次提交附带：`Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>`
- 实现与测试配对提交，每个 commit ≤ 500 行、只做一件事（Phase 各阶段模板见 `collaboration.mdc`）

## 常用命令

```bash
make dev-api      # Python 后端 → 127.0.0.1:8000
make dev-web      # Tauri 桌面应用
make test         # pytest + vitest（eval 不进 CI）
make lint         # ruff + mypy + eslint + vue-tsc
make eval-rag     # RAG 离线评估（需 [eval] extra + 模型下载）
```

## 架构约束

- **分层**：`api → services → domain → shared + infrastructure`（单向依赖）
- **DI**：Agent/Skill 通过构造函数接收 LLM、DB session、Tracer；禁止自行 `ChatOpenAI()` / `SessionLocal()`
- **无副作用**：禁止模块级 `load_dotenv()` 或 `os.environ` 全局写入
- **单用户**：无 MySQL、无 Redis、无 JWT、无 Docker

## 可观测性

每次 LLM 调用写入 `llm_call_logs` 表（agent_name, latency_ms, tokens_in/out, model, tier），Agent 通过 DI 接收 `LLMCallTracer`。Agent 决策写入 `agent_decisions` 表。写入异步完成，不阻塞主流程。

## 降级与韧性

- LLM API 不可达 → 返回预设安全模板，不抛异常
- Crisis 检测命中 → 短路到安全模板
- 每个 Agent 独立超时；Supervisor 容忍部分 Worker 失败，用剩余结果降级合成
- Reranker 模型加载失败 → `fallback()` 返回原始融合序

## 当前状态

✅ Phase A 完成（5/5 PR 已合并）。✅ Phase B-1/B-2/B-3/B-3.5 已合并。▶ 下一步 B-4（`feature/domain-memory`）— 三层记忆系统。

全项目 24 PR（Phase A:5 + B:11 + C:3 + D:4 + E:1）。
