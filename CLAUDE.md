# Night Diary V2

AI 心理陪伴日记系统，支持**双部署模式**：本地桌面端（Tauri + SQLite）和 Web 多用户端（Docker Compose + MySQL + Redis + Neo4j + JWT）。

## 架构现状

### 双部署模式

| 模式 | 场景 | 数据库 | 缓存 | 实体图 | 认证 |
|------|------|--------|------|--------|------|
| 桌面端 | 单用户本地 | SQLite (WAL) | 内存 dict | SQLite DomainKnowledgeStore | 无 |
| Web 端 | 多用户生产 | MySQL (utf8mb4) | Redis | Neo4j | JWT |

所有基础设施组件（Redis / Neo4j / MySQL / RQ）均实现**优雅降级**：不可用时自动回退到内存或 SQLite 方案，失败仅记日志不中断主流程。

### 两大 AI 业务场景

| 维度 | 场景一：写日记 → 回信 | 场景二：会话 → 多轮对话 |
|------|---------------------|----------------------|
| 入口 | `analysis_service.trigger_analysis()` | `conversation_ai_service.generate_reply()` |
| 编排 | ExecutionPlanner → MultiAgentGraph (asyncio 并发) | ConversationLoop / LangGraph StateGraph |
| 意图识别 | IntentClassifier (4 类日记意图) | ChatIntentClassifier (6 类对话意图) + SlotExtractor |
| 输入预处理 | ContentNormalizer 归一化 | InputPreprocessor (清洗 + NFC + 安全 + 省略补齐 + 否定) |
| 工具调用 | agent_executor (ReAct) | ConversationLoop (双路径: native + text-tag) |
| 技能系统 | create_diary_registry() | create_chat_registry() |
| 记忆写入 | MemoryGateway.persist_atom() | MemoryGateway.persist_atom() + _maybe_persist_episodic() |
| 实体提取 | 异步旁置 (source_label="diary") | 异步旁置 (source_label="conversation") |
| LangGraph | 弃用 (纯 asyncio) | 可选启用 (use_graph=True, 降级到 legacy loop) |

两场景通过共享子组件互通：`ContentNormalizer`、`UnifiedMemoryAtom`、`MemoryGateway`、`HybridEntityExtractor`、`OrchestratorProtocol`。

### 中间件角色

- **Redis**：SessionContext L2 缓存 (30min TTL) / JWT 黑名单 / 模型配置缓存 (5min TTL)
- **Neo4j**：实体关系图 `(:User)-[:MENTIONS]->(:Entity)-[:RELATED_TO]->(:Entity)`，降级到 SQLite
- **RQ**：异步旁置任务（实体提取），降级到 daemon thread
- **LangGraph**：场景二 StateGraph 编排（6 节点），降级到 legacy loop
- **MCP**：双向——对外暴露内置工具 (MCPServer) + 对内动态接入外部工具 (build_tool_map_with_mcp)
- **MySQL**：生产主数据库，Alembic 迁移 (render_as_batch)，连接池 + utf8mb4

## Git 规范

- **永远不直接 push main**，所有改动走 PR
- 从 main 开新分支前：`git checkout main && git pull`
- 分支命名：`feature/` / `fix/` / `refactor/` / `chore/` / `docs/`
- 提交用约定式提交：`feat:` `fix:` `chore:` `docs:` 等，原子化
- 提交时不要跳过 hook（不用 `--no-verify`）
- **不 amend 已推送的提交**；pre-commit hook 失败后修复并新建 commit，不 amend
- 每次提交附带：`Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>`

## PR 规范

完成分支工作后 **必须** 通过 PR 合并，严禁直接 push。PR 描述必须包含：

```markdown
## 标题
[一句话说明做了什么，≤70 字符]

## 功能描述
[功能作用与使用方式。Bug 修复需说明现象和根因。]

## 实现思路
[技术选型理由、核心逻辑、关键 trade-off。]

## 测试方式
- [ ] pytest（N 个测试通过）
- [ ] vitest（M 个测试通过）
- [ ] 手动验证：[具体步骤]
```

大型 PR 额外包含 `## 任务拆分` 和 `## 验证清单`。PR 按优先级合并（P0 → P1 → P2）。

## 常用命令

```bash
# 桌面端开发
make dev-api      # Python 后端 → 127.0.0.1:8000
make dev-web      # Tauri 桌面应用（npm run tauri dev）
make dev-web-fast # Tauri attach 模式（不重启后端）

# Web 端开发（Docker）
docker compose up -d                          # 生产模式（MySQL + Redis + 全服务）
docker compose -f docker-compose.yml -f docker-compose.dev.yml up  # 开发模式（SQLite + 内存降级）
docker compose --profile graph up -d neo4j    # 单独启动 Neo4j

# 测试与质量
make test         # pytest + vitest
make lint         # ruff + mypy + eslint + vue-tsc
make eval         # 离线 eval 测试（真实 LLM）
make e2e          # API 端到端流程测试
make smoke        # 性能冒烟检查
```

## AI 工程质量标准

### 可观测性

每次 LLM 调用必须可追溯，存储于本地 SQLite，不上传外部服务：

| 记录类型 | 存储表 | 关键字段 |
|----------|--------|----------|
| LLM 调用 | `llm_call_logs` | agent_name, call_type, prompt, response, latency_ms, tokens_in/out, model, tier |
| Agent 决策 | `agent_decisions` | agent_name, decision_type, input_summary, output, reason |

- Agent 通过 DI 接收 `LLMCallTracer`，与 LLM、DB session 同级
- 写入异步完成，不阻塞 Agent 主流程

### 测试理念

- **单元测试 mock LLM**：验证 Agent 控制流（路由、fan-out、合成、降级）
- **Eval 测试真实 LLM**：`server/tests/eval/` 下固定输入 + 结构化评判标准，prompt 改动后手动跑 `make eval`
- **统计测试**：Thompson Sampling 跑 N≥1000 验证 Beta 分布，不依赖单次断言
- **级联失败测试**：RetrievalAgent 多跳检索漂移场景、Worker 超时降级、基础设施不可用降级

### 降级与韧性

- **LLM 不可达**：返回预设安全模板，不白屏或抛异常
- **Crisis 检测命中**：短路到安全模板，不送 LLM（场景二双重安全网：Stage 2 + Stage 2.5）
- **Redis 不可用**：SessionContext 降级为纯内存 dict，JWT 黑名单降级为内存集合
- **Neo4j 不可用**：实体提取仍运行但仅记日志，查询返回"不可用"提示，降级到 SQLite
- **MySQL 不可用**：桌面端始终可用 SQLite fallback
- **LangGraph 不可用**：场景二自动降级到 legacy loop（同步 for 循环）
- **MCP 加载失败**：仅记日志，不阻塞内置工具
- 每个 Agent 独立超时：Supervisor 最长，Worker 较短
- Supervisor 容忍部分 Worker 失败：如 Retrieval 挂了，用剩余 Worker 结果降级合成

### 记忆层约束

- Memory 层操作必须包含 `user_id` 参数（多租户隔离）
- `EpisodicEntry` 必须包含 `source` 字段（`'diary'` / `'chat'` / `'card'`）
- `UnifiedMemoryAtom` 是日记/卡片/对话的统一写入路径
- MemoryGateway 四维检查：内容有效性 / 危机污染 / 情感显著性 / 去重
- 记忆晋升长期存储使用 tags 匹配，不使用原始文本匹配
- RAG 三源有序检索：日记记忆 → 夜话共鸣 → 情绪卡片

## 当前状态

✅ Phase A–E（桌面端 MVP）+ Phase 1–3（Web 多用户架构 + 基础设施）+ Agent 架构优化（P1–P3 共 10 个任务）全部完成。

- 后端测试：509+ 通过
- 双部署模式可用：桌面端（Tauri + SQLite）和 Web 端（Docker Compose）
- Agent 架构：InputPreprocessor / SlotExtractor / HybridEntityExtractor / LangGraph StateGraph / OrchestratorProtocol / Citation 系统 / MCP 集成 / 统一反馈通道
- 架构分析文档：`.trae/documents/agent架构深度分析与优化实施计划.md`
- 数据链路报告：`agent-data-flow/agent-data-flow.html`
