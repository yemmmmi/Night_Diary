# Night Diary V2 — 任务总纲

> **仓库级施工蓝图**（非 Cursor Plan 文件）。每个 **PR = 下方一个章节**，含 `Implementation Plan` 三段式。  
> **V1 只读参考**：`D:\work\night_diary`（不可修改）。**架构/协作细则**：`.cursor/rules/` 下 `architecture.mdc`、`collaboration.mdc`、`coding-standards.mdc`、`execution-plan.mdc`。

---

## 0. 如何使用本文

1. 按 **Phase 顺序**执行；Phase 2 内按 PR 编号 **2.1 → 2.6** 依赖顺序合并。
2. 开始 PR 前：`git checkout main && git pull && git checkout -b <Branch>`（见各章节）。
3. 将对应章节的 **Tasks** 复制到 PR 描述（与 `.github/pull_request_template.md` 一致）。
4. **合并标准**：该 PR 的 Verification 全部通过，且 `main` 可运行（`make up` / `make test` / 该阶段手动流）。
5. 当前应执行的 PR：见 `.cursor/rules/current_phase.mdc`（随进度更新）。

**累计 PR 数**：18（Phase 0:1 + 1:1 + 2:6 + 3:2 + 4:5 + 5:3）

---

## 1. 全局约定

| 项 | 约定 |
|----|------|
| 主分支 | 禁止直接向 `main` push；必须 PR 合并 |
| 分支命名 | `feature/`、`fix/`、`chore/`、`refactor/`、`docs/`、`test/`、`perf/`（见 `collaboration.mdc`） |
| 提交 | 约定式提交：`feat:`、`fix:`、`chore:` 等，原子提交 |
| 分层 | `api → services → domain → shared + infrastructure`（单向） |
| 错误 | 服务层抛 `AppError` 子类，路由层转换 HTTP |
| DI | Agent/Skill 通过构造函数接收 LLM、DB session，禁止 `SessionLocal()` / 自行 `ChatOpenAI()` |
| V2 独立性 | 绝不 import V1 代码 |

---

## 2. 部署与环境策略

### 本地开发（Phase 0 起）

```text
web :5173 (Vite)  --VITE_API_BASE_URL-->  server :8000 (FastAPI)
                                              |
                                    docker-compose (MySQL 8, Redis 7)
                                              |
                                    ./chroma_data (Chroma 本地卷，RAG/knowledge 使用)
```

### 环境变量（`config.py` / `.env.example`，禁止硬编码 host）

| 变量 | 本地默认 | 云上扩展 |
|------|----------|----------|
| `DATABASE_URL` | `mysql+pymysql://...@localhost:3306/...` | 托管 MySQL；`server/.env.production.example` 注明 SSL |
| `REDIS_URL` | `redis://localhost:6379/0` | 云 Redis URL |
| `ALLOWED_ORIGINS` | `http://localhost:5173` | 生产前端域名，逗号分隔 |
| `CHROMA_PERSIST_DIR` | `./chroma_data` | 同卷或 Phase 5 文档中的 `CHROMA_HOST` 占位 |
| `VITE_API_BASE_URL` | `http://localhost:8000` | 构建时注入 `https://api.example.com` |
| `APP_ENV` | `development` | `production`（日志/OpenAPI 开关） |
| `JWT_SECRET_KEY` | 必填，无 fallback | 同上 |
| `MODEL_KEY_SECRET` | 必填，独立于 JWT | 同上 |
| `TRUSTED_PROXY_IPS` | 空或本地代理 | 受信代理 IP 列表（限流/锁） |

### Makefile 目标（Phase 0 交付）

`make up` / `make down` / `make migrate` / `make dev-api` / `make dev-web` / `make test` / `make lint`（与 CI 一致）

---

## PR: phase-0-project-scaffold

- **Branch**: `chore/project-scaffold`
- **Depends on**: —
- **合并后 main**: `make up` + `make migrate` + `GET /health` 200 + Vue 占位首页 + CI 绿

### Implementation Plan

#### Overview

搭建 monorepo 目录、本地 Docker 基础设施、双端工具链与 CI；配置按环境变量设计，云上仅换 env。

#### Tasks

- [ ] 1. [核心] 目录结构 — 按 `architecture.mdc` 创建 `server/`、`web/`、`alembic/`、`.github/workflows/`、`server/app/{api,services,domain,shared,infrastructure}/`、`web/src/{pages,features,shared,router}/`
- [ ] 2. [核心] `server/pyproject.toml` — 依赖 FastAPI、SQLAlchemy 2、alembic、pydantic-settings、redis、pytest、ruff、mypy
- [ ] 3. [核心] `server/app/config.py` — `Settings`：`DATABASE_URL`、`REDIS_URL`、`ALLOWED_ORIGINS`、`APP_ENV`、`JWT_SECRET_KEY`、`MODEL_KEY_SECRET`、`CHROMA_PERSIST_DIR`；启动校验必填项
- [ ] 4. [核心] `server/app/main.py` — `GET /health` → `{"status":"ok"}`；CORS 读 `ALLOWED_ORIGINS`
- [ ] 5. [核心] `server/.env.example` — 对齐上表变量 + 云库 SSL 注释块
- [ ] 6. [核心] `web/package.json`、`web/vite.config.ts`、`web/tsconfig.json`、`web/tailwind.config.js`、`web/index.html`
- [ ] 7. [核心] `web/src/main.ts`、`web/src/App.vue` — 占位「Night Diary V2」
- [ ] 8. [核心] `web/.env.example` — `VITE_API_BASE_URL=http://localhost:8000`
- [ ] 9. [核心] `docker-compose.yml` — `mysql:8`、`redis:7`；卷 `mysql_data`、`redis_data`；端口映射文档说明（应用连 `localhost`）
- [ ] 10. [核心] `alembic.ini` + `alembic/env.py` — 从 `Settings.DATABASE_URL` 读取
- [ ] 11. [核心] 根目录 `Makefile` — `up`/`down`/`migrate`/`dev-api`/`dev-web`/`test`/`lint`
- [ ] 12. [CI] `.github/workflows/ci.yml` — pytest、vitest、mypy、vue-tsc、ruff、eslint（空测试可通过）
- [ ] 13. [CI] `.pre-commit-config.yaml` + `.github/pull_request_template.md`（含 Implementation Plan 模板）
- [ ] 14. [文档] `README.md` — `cp server/.env.example` → `make up` → `make migrate` → `make dev-api` / `make dev-web`

#### Verification

1. `docker compose up -d` 后 MySQL/Redis 健康
2. `make migrate` 无报错（可无业务表）
3. `curl localhost:8000/health` → 200；浏览器 `localhost:5173` 可打开
4. Push 后 GitHub Actions 全绿

---

## PR: phase-1-infrastructure-layer

- **Branch**: `feature/infrastructure-layer`
- **Depends on**: phase-0
- **合并后 main**: `make migrate` 建全表；`pytest server/tests` 通过；缺 `JWT_SECRET_KEY` 启动失败

### Implementation Plan

#### Overview

ORM、初始 schema、安全、Redis、统一错误与 LLM 工厂就位。

#### Tasks

- [ ] 1. [核心] `server/app/infrastructure/database.py` — SQLAlchemy 2.0 引擎/Session；`pool_pre_ping=True`、`pool_recycle=3600`
- [ ] 2. [核心] `server/app/infrastructure/models/__init__.py` — 导出全部模型
- [ ] 3. [核心] `server/app/infrastructure/models/user.py` — `User`
- [ ] 4. [核心] `server/app/infrastructure/models/diary_entry.py` — `DiaryEntry`
- [ ] 5. [核心] `server/app/infrastructure/models/analysis.py` — `Analysis`；含 **`execution_tier`** 列（`String(16)`，可空，为 Phase 2/3 预留）
- [ ] 6. [核心] `server/app/infrastructure/models/tag.py` — `Tag`
- [ ] 7. [核心] `server/app/infrastructure/models/diary_tag.py` — **显式** `DiaryTag` 关联模型（非裸 `Table`）
- [ ] 8. [核心] `server/app/infrastructure/models/model_provider.py` — `ModelProvider`
- [ ] 9. [核心] `server/app/infrastructure/models/feedback.py` — `Feedback`
- [ ] 10. [核心] `server/app/infrastructure/models/style_preference.py` — `StylePreference`
- [ ] 11. [核心] `server/app/infrastructure/models/knowledge_entry.py` — `KnowledgeEntry`；`long_term_profile`、`entity_data` 用 **MySQL JSON**
- [ ] 12. [核心] Alembic — `alembic revision --autogenerate -m "initial_schema"`；`alembic/versions/*.py` 入库
- [ ] 13. [核心] `server/app/infrastructure/security.py` — JWT + bcrypt；`hash_password`/`verify_password`/`create_access_token`/`decode_token`；**无 fallback secret**
- [ ] 14. [核心] `server/app/shared/errors.py` — `AppError`、`AuthError`、`DiaryError`、`AnalysisError`、`ValidationError`；`http_status` 映射
- [ ] 15. [核心] `server/app/shared/llm.py` — `LLMFactory.create(provider|settings)`；支持用户 `ModelProvider`
- [ ] 16. [核心] `server/app/infrastructure/redis.py` — 连接池；不可用则 **启动失败**（非 `Optional` 静默降级）
- [ ] 17. [核心] `server/app/infrastructure/distributed_lock.py` — 从 V1 `core/distributed_lock.py` 迁移
- [ ] 18. [核心] `server/app/infrastructure/rate_limiter.py` — 从 V1 迁移；`get_client_ip()` 尊重 `TRUSTED_PROXY_IPS`
- [ ] 19. [核心] `server/app/config.py` — 增加 `TRUSTED_PROXY_IPS: list[str]`
- [ ] 20. [核心] `server/app/di.py` — 骨架：`get_db`、`get_redis`（Phase 3 扩展）
- [ ] 21. [测试] `server/tests/conftest.py` — SQLite 内存库 / Redis mock fixtures
- [ ] 22. [测试] `server/tests/unit/test_errors.py`、`test_security.py`、`test_rate_limiter.py`、`test_distributed_lock.py`

#### Verification

1. `make migrate` 在本地 MySQL 建表成功
2. `pytest server/tests -v` 通过
3. 未设置 `JWT_SECRET_KEY` 时 `uvicorn` 启动失败

---

## PR: phase-2-1-domain-knowledge

- **Branch**: `feature/domain-knowledge`
- **Depends on**: phase-1
- **合并后 main**: `DomainKnowledgeStore` 可单元测试；Chroma 目录可配置

### Implementation Plan

#### Overview

领域知识库作为 **唯一** Chroma 查询入口；后续 RAG 与 Agent 均依赖本模块。

#### Tasks

- [ ] 1. [核心] `server/app/domain/knowledge/__init__.py`
- [ ] 2. [核心] `server/app/domain/knowledge/store.py` — `DomainKnowledgeStore`：迁移 V1 `domain_store.py`；`query()`、`add()`、`delete()`；读 `Settings.CHROMA_PERSIST_DIR`
- [ ] 3. [核心] `server/app/domain/knowledge/extractor.py` — 迁移 V1 extractor；修复 `entity_type` 文档与实现不一致
- [ ] 4. [核心] `server/app/domain/knowledge/types.py` — `KnowledgeHit`、`EntityRecord` 等 dataclass/TypedDict
- [ ] 5. [测试] `server/tests/unit/domain/knowledge/test_store.py` — mock Chroma client
- [ ] 6. [测试] `server/tests/unit/domain/knowledge/test_extractor.py`

#### Verification

1. `pytest server/tests/unit/domain/knowledge -v` 通过
2. 无模块级 `load_dotenv()`；配置仅来自 `config.py`

---

## PR: phase-2-2-domain-rag

- **Branch**: `feature/domain-rag`
- **Depends on**: phase-2-1-domain-knowledge
- **合并后 main**: 日记向量同步可调用 `HybridRetriever`（单元测试 mock）

### Implementation Plan

#### Overview

将 V1 `vector_service.py`（771 行）拆为 4 模块 + collection 管理；消除全局副作用。

#### Tasks

- [ ] 1. [核心] `server/app/domain/rag/__init__.py`
- [ ] 2. [核心] `server/app/domain/rag/chunker.py` — `ChunkSplitter`；合并 V1 `ParentChildChunker` 逻辑
- [ ] 3. [核心] `server/app/domain/rag/bm25.py` — `BM25Index` **类实例**（非模块级 dict，防内存泄漏）
- [ ] 4. [核心] `server/app/domain/rag/retriever.py` — `HybridRetriever`：向量 + BM25；依赖 `DomainKnowledgeStore` 做 collection 名约定
- [ ] 5. [核心] `server/app/domain/rag/reranker.py` — `Reranker`；**实例级** 配置，禁止 `os.environ` 全局写入
- [ ] 6. [核心] `server/app/domain/rag/collections.py` — `DiaryCollectionManager`：用户日记 collection 生命周期
- [ ] 7. [测试] `server/tests/unit/domain/rag/test_chunker.py`
- [ ] 8. [测试] `server/tests/unit/domain/rag/test_bm25.py`
- [ ] 9. [测试] `server/tests/unit/domain/rag/test_retriever.py` — mock embedding
- [ ] 10. [测试] `server/tests/unit/domain/rag/test_reranker.py`

#### Verification

1. `pytest server/tests/unit/domain/rag -v` 通过
2. 全库 grep 无 `vector_service` 引用（V2 新代码）

---

## PR: phase-2-3-domain-memory

- **Branch**: `feature/domain-memory`
- **Depends on**: phase-1
- **合并后 main**: 三层记忆 API 可测；`WorkingMemory` 有集成测试桩

### Implementation Plan

#### Overview

迁移 V1 记忆模块并修复已知问题；为 Phase 2.5 skills 与 2.6 agents 提供记忆读写。

#### Tasks

- [ ] 1. [核心] `server/app/domain/memory/__init__.py`
- [ ] 2. [核心] `server/app/domain/memory/episodic.py` — `EpisodicMemory`；修复 V1 **query 参数未使用** 问题
- [ ] 3. [核心] `server/app/domain/memory/long_term.py` — `LongTermMemory`；JSON 画像读写
- [ ] 4. [核心] `server/app/domain/memory/working.py` — `WorkingMemory`；会话级上下文
- [ ] 5. [核心] `server/app/domain/memory/types.py` — `MemoryContext`、`Episode` 等
- [ ] 6. [测试] `server/tests/unit/domain/memory/test_episodic.py`
- [ ] 7. [测试] `server/tests/unit/domain/memory/test_long_term.py`
- [ ] 8. [测试] `server/tests/unit/domain/memory/test_working.py`

#### Verification

1. `pytest server/tests/unit/domain/memory -v` 通过
2. `EpisodicMemory.search(query=...)` 断言结果受 query 影响

---

## PR: phase-2-4-domain-feedback

- **Branch**: `feature/domain-feedback`
- **Depends on**: phase-1
- **合并后 main**: Thompson + PromptTuner 无重复采样逻辑

### Implementation Plan

#### Overview

迁移 Thompson Sampling；PromptTuner 委托 Thompson，删除 V1 重复实现。

#### Tasks

- [ ] 1. [核心] `server/app/domain/feedback/__init__.py`
- [ ] 2. [核心] `server/app/domain/feedback/thompson.py` — 迁移 V1 `thompson_sampling.py`：`ThompsonSampling.sample_style()`
- [ ] 3. [核心] `server/app/domain/feedback/prompt_tuner.py` — `PromptTuner`；`_sample_style_from_preferences()` **调用** `ThompsonSampling`，不重复 Beta 采样
- [ ] 4. [核心] `server/app/domain/feedback/prompt_tuner.py` — 实现 `_infer_response_length()` 真实逻辑（V1 stub 始终 MEDIUM）
- [ ] 5. [测试] `server/tests/unit/domain/feedback/test_thompson.py`
- [ ] 6. [测试] `server/tests/unit/domain/feedback/test_prompt_tuner.py`

#### Verification

1. `pytest server/tests/unit/domain/feedback -v` 通过
2. PromptTuner 单测 mock Thompson，断言只调用一次采样

---

## PR: phase-2-5-domain-skills

- **Branch**: `feature/domain-skills`
- **Depends on**: phase-2-3-domain-memory, phase-2-4-domain-feedback
- **合并后 main**: `SkillRegistry.select_skills()` 有集成测试；10 个 Skill 注册完成

### Implementation Plan

#### Overview

迁移 V1 Skill 系统并通过 DI 注入依赖；为 Supervisor（2.6）提供技能驱动路由。

#### Tasks

- [ ] 1. [核心] `server/app/domain/skills/base.py` — `BaseSkill`、`SkillResult`；迁移 V1 `base.py`
- [ ] 2. [核心] `server/app/domain/skills/registry.py` — `SkillRegistry.register()`、`select_skills()`、`get_skill()`
- [ ] 3. [核心] `server/app/domain/skills/implementations/crisis_detector.py` — 迁移；情感估计不重复 agents 层
- [ ] 4. [核心] `server/app/domain/skills/implementations/sentiment_skill.py`
- [ ] 5. [核心] `server/app/domain/skills/implementations/weather_skill.py`
- [ ] 6. [核心] `server/app/domain/skills/implementations/search_diary_skill.py`
- [ ] 7. [核心] `server/app/domain/skills/implementations/address_skill.py`
- [ ] 8. [核心] `server/app/domain/skills/implementations/memory_reader.py`
- [ ] 9. [核心] `server/app/domain/skills/implementations/memory_writer.py`
- [ ] 10. [核心] `server/app/domain/skills/implementations/habit_tracker.py`
- [ ] 11. [核心] `server/app/domain/skills/implementations/pattern_detector.py`
- [ ] 12. [核心] `server/app/domain/skills/implementations/summary_generator.py`
- [ ] 13. [核心] `server/app/domain/skills/bootstrap.py` — `register_default_skills(registry, di)` 集中注册
- [ ] 14. [核心] 各 Skill `__init__` 接收 `llm`、`db`/`memory` 等，禁止自行创建 LLM
- [ ] 15. [测试] `server/tests/unit/domain/skills/test_registry.py` — register + select 优先级
- [ ] 16. [测试] `server/tests/unit/domain/skills/test_crisis_detector.py`
- [ ] 17. [测试] `server/tests/integration/domain/skills/test_skill_selection.py`

#### Verification

1. `pytest server/tests -k skills -v` 通过
2. `SkillRegistry` 默认注册 10 个实现（与 V1 对齐）

---

## PR: phase-2-6-domain-agents

- **Branch**: `feature/domain-agents`
- **Depends on**: phase-2-1 ~ 2-5 全部合并
- **合并后 main**: Supervisor 输出 `execution_tier` + `intent`；graph 单测通过

### Implementation Plan

#### Overview

Multi-Agent 协调层；删除硬编码 `DEFAULT_INTENT_ROUTING`；共享知识/情感/Token 工具；危机短路在图外定义（与 Phase 3 `ai_router` 衔接）。

#### Tasks

- [ ] 1. [核心] `server/app/domain/agents/types.py` — `ExecutionTier` 枚举：`light`/`medium`/`heavy`；`AgentIntent` 字符串常量
- [ ] 2. [核心] `server/app/domain/agents/state.py` — `MultiAgentState`；修复 V1 reducer 不一致
- [ ] 3. [核心] `server/app/domain/agents/intent.py` — `IntentClassifier`；迁移 V1 `intent_classifier.py`
- [ ] 4. [核心] `server/app/domain/agents/supervisor.py` — `SupervisorAgent`：DI 注入 `llm`、`SkillRegistry`；`classify()` 调 `select_skills()`；输出 `intent`、`execution_tier`、选中 skill 列表
- [ ] 5. [核心] `server/app/domain/agents/graph.py` — `MultiAgentGraphBuilder`；**删除** `DEFAULT_INTENT_ROUTING`；路由由 skill/supervisor 输出决定 Worker
- [ ] 6. [核心] `server/app/domain/agents/shared/emotion_estimator.py` — 唯一情感估计入口（供 empathy + crisis）
- [ ] 7. [核心] `server/app/domain/agents/shared/token_estimator.py`
- [ ] 8. [核心] `server/app/domain/agents/workers/base.py` — `BaseWorker.run(state) -> state`
- [ ] 9. [核心] `server/app/domain/agents/workers/empathy.py` — DI LLM + `DomainKnowledgeStore` + `EmotionEstimator`
- [ ] 10. [核心] `server/app/domain/agents/workers/retrieval.py` — DI LLM + knowledge + `TokenEstimator` + `HybridRetriever`
- [ ] 11. [核心] `server/app/domain/agents/workers/insight.py` — DI LLM + knowledge
- [ ] 12. [核心] `server/app/domain/agents/crisis.py` — `CrisisHandler`：图入口前短路文档 + 函数（返回安全模板，`execution_tier=light`）
- [ ] 13. [核心] 图内仅 `medium`/`heavy` 走 LangGraph 全路径；`light` 不进入图（由 executor 层消费，见 Phase 3）
- [ ] 14. [测试] `server/tests/unit/domain/agents/test_intent.py`
- [ ] 15. [测试] `server/tests/unit/domain/agents/test_supervisor.py` — mock skills 降级
- [ ] 16. [测试] `server/tests/unit/domain/agents/test_graph_routing.py`
- [ ] 17. [测试] `server/tests/unit/domain/agents/test_crisis_short_circuit.py`

#### Verification

1. `pytest server/tests/unit/domain/agents -v` 通过
2. `graph.py` 中无 `DEFAULT_INTENT_ROUTING` 字符串
3. Worker 单测断言不实例化 `ChatOpenAI()`（mock DI）

---

## PR: phase-3-1-services-layer

- **Branch**: `feature/services-layer`
- **Depends on**: phase-2-6
- **合并后 main**: 服务层单测通过；`ExecutionPlanner` 降级链可测

### Implementation Plan

#### Overview

业务编排与 AI 执行拆分；替代 V1 `ai_service.py` 三模式为 **tier 驱动** 执行器。

#### Tasks

- [ ] 1. [核心] `server/app/services/auth_service.py` — `register`、`login`、`get_current_user`；抛 `AuthError`，无 `HTTPException`
- [ ] 2. [核心] `server/app/services/diary_service.py` — CRUD；`sync_vector()` 调 `domain/rag`
- [ ] 3. [核心] `server/app/services/analysis_service.py` — 防重锁；写 `execution_tier`；兼容写入 `agent_mode`；`_get_recent_entries()` 提取 7 天查询
- [ ] 4. [核心] `server/app/services/admin_service.py` — 用户/日记/分析/知识库管理（从 V1 `routers/admin.py` 抽出）
- [ ] 5. [核心] `server/app/services/token_stats_service.py` — Token 聚合（从 V1 `routers/token_stats.py` 抽出）
- [ ] 6. [核心] `server/app/services/feedback_service.py` — 显式/隐式反馈持久化
- [ ] 7. [核心] `server/app/services/ai_router.py` — `ExecutionPlanner`：`classify → plan(tier) → execute`；危机先 `CrisisHandler`
- [ ] 8. [核心] `server/app/services/ai_prompts.py` — 全部 prompt 模板
- [ ] 9. [核心] `server/app/services/ai_executors/light.py` — 单次 LLM（原 chain 路径）
- [ ] 10. [核心] `server/app/services/ai_executors/medium.py` — 单 Worker + synthesize
- [ ] 11. [核心] `server/app/services/ai_executors/heavy.py` — LangGraph 全图
- [ ] 12. [核心] `server/app/services/ai_tools.py` — 工具工厂；**不保留** 独立 `agent.py` executor
- [ ] 13. [核心] `ai_router.py` — 降级链：`heavy → medium → light → FALLBACK` 常量响应
- [ ] 14. [核心] `server/app/di.py` — 注册 services 与 executors 工厂
- [ ] 15. [测试] `server/tests/unit/services/test_auth_service.py`
- [ ] 16. [测试] `server/tests/unit/services/test_analysis_service.py`
- [ ] 17. [测试] `server/tests/unit/services/test_ai_router.py` — mock LLM，断言 tier 与降级

#### Verification

1. `pytest server/tests/unit/services -v` 通过
2. `analysis_service` 单测：`pure_record` 路径写入 `execution_tier=light`

---

## PR: phase-3-2-api-routes

- **Branch**: `feature/api-routes`
- **Depends on**: phase-3-1
- **合并后 main**: `register → login → diary → POST /analysis` 集成测试绿

### Implementation Plan

#### Overview

薄路由层 + 统一错误转换；`main.py` lifespan 初始化 Redis。

#### Tasks

- [ ] 1. [核心] `server/app/api/deps.py` — `get_db`、`get_current_user`、`require_admin`
- [ ] 2. [核心] `server/app/api/errors.py` — `app_error_handler(AppError)`
- [ ] 3. [核心] `server/app/api/v1/auth.py` — `/register`、`/login`、`/me`
- [ ] 4. [核心] `server/app/api/v1/diary.py` — 日记 CRUD + 列表分页
- [ ] 5. [核心] `server/app/api/v1/analysis.py` — `POST /diary/{id}/analysis`
- [ ] 6. [核心] `server/app/api/v1/feedback.py`
- [ ] 7. [核心] `server/app/api/v1/tags.py`
- [ ] 8. [核心] `server/app/api/v1/models.py` — 用户 LLM 提供商配置
- [ ] 9. [核心] `server/app/api/v1/weather.py`
- [ ] 10. [核心] `server/app/api/v1/admin.py` — 仅调 `admin_service`
- [ ] 11. [核心] `server/app/api/v1/token_stats.py`
- [ ] 12. [核心] `server/app/api/v1/public_column.py`
- [ ] 13. [核心] `server/app/api/v1/router.py` — 聚合挂载 `/api/v1`
- [ ] 14. [核心] `server/app/main.py` — lifespan：Redis ping；`embedding_warmup()` 空实现钩子（Phase 5 实现）
- [ ] 15. [测试] `server/tests/integration/api/test_auth_flow.py`
- [ ] 16. [测试] `server/tests/integration/api/test_diary_analysis_flow.py`

#### Verification

1. `pytest server/tests/integration -v` 通过
2. 本地手动：`pure_record` 日记分析后 DB 中 `execution_tier=light`

---

## PR: phase-4-1-frontend-foundation

- **Branch**: `feature/frontend-foundation`
- **Depends on**: phase-3-2（API 可用）
- **合并后 main**: `npm run build` + vitest 基础通过

### Implementation Plan

#### Overview

共享类型、HTTP 客户端、通用 composables 与布局；消除 V1 重复工具与 `any`。

#### Tasks

- [ ] 1. [核心] `web/src/shared/types/index.ts` — `User`、`DiaryEntry`、`Analysis`、`PaginatedResponse`、`ExecutionTier` 等（无 `any`）
- [ ] 2. [核心] `web/src/shared/api/http.ts` — axios 实例、JWT 拦截器、401 跳转
- [ ] 3. [核心] `web/src/shared/api/auth.ts`、`diary.ts`、`analysis.ts`、`feedback.ts`、`tags.ts`、`models.ts`、`admin.ts`、`tokenStats.ts`、`column.ts` — 完整返回类型
- [ ] 4. [核心] `web/src/shared/utils/date.ts` — `formatDate`、`formatTime`、`formatDateTime`
- [ ] 5. [核心] `web/src/shared/utils/format.ts` — 通用格式化
- [ ] 6. [核心] `web/src/shared/composables/useErrorHandler.ts` — `getErrorMessage(err)`
- [ ] 7. [核心] `web/src/shared/composables/usePagination.ts` — `page`、`pageSize`、`total`、`setPage`
- [ ] 8. [核心] `web/src/shared/composables/useTheme.ts` — 修复 V1 多 `onUnmounted` 竞态
- [ ] 9. [核心] `web/src/shared/components/AppLayout.vue` — 顶栏、导航、`router-view`
- [ ] 10. [核心] `web/src/shared/components/WeatherWidget.vue` — **props**: `weatherInfo`（不 import auth store）
- [ ] 11. [核心] `web/vite.config.ts` — `server.proxy` 可选 `/api` → `localhost:8000`
- [ ] 12. [核心] `web/.env.example` — `VITE_API_BASE_URL` + 云构建注释
- [ ] 13. [测试] `web/src/shared/composables/__tests__/useErrorHandler.spec.ts`
- [ ] 14. [测试] `web/src/shared/composables/__tests__/usePagination.spec.ts`
- [ ] 15. [测试] `web/src/shared/composables/__tests__/useTheme.spec.ts`

#### Verification

1. `cd web && npm run build && npm run test`
2. `vue-tsc --noEmit` 零错误

---

## PR: phase-4-2-frontend-auth

- **Branch**: `feature/frontend-auth`
- **Depends on**: phase-4-1
- **合并后 main**: 登录/注册/个人资料流可用

### Implementation Plan

#### Overview

认证 Pinia store 与页面；天气数据与 auth 解耦。

#### Tasks

- [ ] 1. [核心] `web/src/shared/stores/auth.ts` — `login`、`logout`、`register`、`fetchMe`；token 持久化
- [ ] 2. [核心] `web/src/shared/stores/weather.ts` — `fetchWeather()`（或 composable `useWeather`）
- [ ] 3. [核心] `web/src/features/auth/composables/useAuth.ts` — 包装 store 供页面使用
- [ ] 4. [核心] `web/src/pages/LoginPage.vue`
- [ ] 5. [核心] `web/src/pages/RegisterPage.vue`
- [ ] 6. [核心] `web/src/pages/ProfilePage.vue`
- [ ] 7. [核心] `web/src/router/index.ts` — 路由表 + `requiresAuth` / `requiresGuest`
- [ ] 8. [核心] `web/src/router/guards.ts` — `setupAuthGuards(router)`
- [ ] 9. [测试] `web/src/router/__tests__/guards.spec.ts`
- [ ] 10. [测试] `web/src/features/auth/composables/__tests__/useAuth.spec.ts`

#### Verification

1. 手动：注册 → 登录 → `/profile`；刷新保持登录
2. `WeatherWidget` 仅通过 prop/store 注入，不读 `auth.weather`

---

## PR: phase-4-3-frontend-diary

- **Branch**: `feature/frontend-diary`
- **Depends on**: phase-4-2
- **合并后 main**: 日记 + AI 分析 + 反馈 UI 完整

### Implementation Plan

#### Overview

日记核心业务与 AI 面板；页面逻辑下沉 composables（非 God Page）。

#### Tasks

- [ ] 1. [核心] `web/src/features/diary/composables/useDiaryList.ts` — 列表、分页、刷新
- [ ] 2. [核心] `web/src/features/diary/composables/useDiaryEditor.ts` — 创建/编辑/自动保存
- [ ] 3. [核心] `web/src/features/diary/components/DiaryList.vue`
- [ ] 4. [核心] `web/src/features/diary/components/DiaryEditor.vue`
- [ ] 5. [核心] `web/src/pages/DiaryPage.vue` — 组合 composables + 子组件
- [ ] 6. [核心] `web/src/features/analysis/composables/useAnalysis.ts` — 触发分析、轮询/状态
- [ ] 7. [核心] `web/src/features/analysis/composables/useImplicitFeedback.ts` — 迁移 V1 三信号逻辑
- [ ] 8. [核心] `web/src/features/analysis/components/AIAnalysisPanel.vue` — 展示 `execution_tier` / `agent_mode`
- [ ] 9. [核心] `web/src/features/analysis/components/FeedbackButtons.vue`
- [ ] 10. [测试] `web/src/features/diary/components/__tests__/DiaryList.spec.ts`
- [ ] 11. [测试] `web/src/features/diary/components/__tests__/DiaryEditor.spec.ts`
- [ ] 12. [测试] `web/src/features/analysis/components/__tests__/AIAnalysisPanel.spec.ts`

#### Verification

1. 手动：写日记 → 触发分析 → 点赞/点踩反馈
2. vitest 上述 3 组件测试通过

---

## PR: phase-4-4-frontend-dashboard

- **Branch**: `feature/frontend-dashboard`
- **Depends on**: phase-4-1
- **合并后 main**: Token 仪表盘可展示 tier 统计

### Implementation Plan

#### Overview

Token 用量可视化；复用 `AppLayout` 与 `usePagination`。

#### Tasks

- [ ] 1. [核心] `web/src/features/dashboard/composables/useTokenStats.ts` — 调 `tokenStatsApi`
- [ ] 2. [核心] `web/src/features/dashboard/components/TokenUsageChart.vue` — Chart.js 配置抽离
- [ ] 3. [核心] `web/src/features/dashboard/components/TierBreakdownTable.vue` — 按 `execution_tier` 聚合展示
- [ ] 4. [核心] `web/src/pages/TokenDashboardPage.vue`
- [ ] 5. [核心] `web/src/router/index.ts` — 增加 `/dashboard` 路由（admin 或登录用户）
- [ ] 6. [测试] `web/src/features/dashboard/composables/__tests__/useTokenStats.spec.ts`

#### Verification

1. 手动：登录后打开仪表盘，有数据时图表渲染
2. `npm run build` 通过

---

## PR: phase-4-5-frontend-admin

- **Branch**: `feature/frontend-admin`
- **Depends on**: phase-4-1, phase-4-2（admin 守卫）
- **合并后 main**: Admin + tags/models/column 页面齐全；vitest 累计 50+

### Implementation Plan

#### Overview

管理端与附属功能页；`adminApi` 全类型；拆分 V1 AdminPage 内联组件。

#### Tasks

- [ ] 1. [核心] `web/src/shared/components/DataTablePagination.vue` — 从 V1 Admin 内联分页抽出
- [ ] 2. [核心] `web/src/features/admin/components/UserTable.vue`
- [ ] 3. [核心] `web/src/features/admin/components/DiaryModerationPanel.vue`
- [ ] 4. [核心] `web/src/pages/AdminPage.vue` — 组合上述组件，无 `any`
- [ ] 5. [核心] `web/src/features/tags/pages/TagsPage.vue`
- [ ] 6. [核心] `web/src/features/models/pages/ModelsPage.vue` — LLM 提供商 UI
- [ ] 7. [核心] `web/src/features/column/components/ColumnDiaryCard.vue`
- [ ] 8. [核心] `web/src/features/column/components/ColumnDiaryDetail.vue`
- [ ] 9. [核心] `web/src/features/column/pages/ColumnPage.vue`
- [ ] 10. [核心] `web/src/router/index.ts` — `requiresAdmin` 路由
- [ ] 11. [测试] `web/src/features/admin/components/__tests__/UserTable.spec.ts`
- [ ] 12. [测试] `web/src/router/__tests__/adminGuard.spec.ts`

#### Verification

1. 管理员账号可进 `/admin`；非管理员 403/重定向
2. `npm run test` 全绿，用例数 ≥ 50

---

## PR: phase-5-1-e2e-tests

- **Branch**: `test/e2e-tests`
- **Depends on**: phase-4-3 至少
- **合并后 main**: `make e2e` 或 CI job 可跑核心流

### Implementation Plan

#### Overview

Playwright 覆盖注册→登录→日记→分析→反馈。

#### Tasks

- [ ] 1. [核心] `e2e/playwright.config.ts` — baseURL `http://localhost:5173`
- [ ] 2. [核心] `e2e/fixtures/auth.ts` — 注册/登录 helper
- [ ] 3. [核心] `e2e/tests/smoke.spec.ts` — 健康检查
- [ ] 4. [核心] `e2e/tests/diary-analysis.spec.ts` — 完整用户流
- [ ] 5. [核心] 根 `Makefile` — `e2e` 目标（启动 compose + api + web 或文档化顺序）
- [ ] 6. [CI] `.github/workflows/ci.yml` — 可选 `e2e` job（`continue-on-error` 或 nightly）

#### Verification

1. 本地 `make e2e` 通过（或 README  documented 三步启动后 `npx playwright test`）
2. PR 附失败截图策略说明

---

## PR: phase-5-2-perf-optimizations

- **Branch**: `perf/optimizations`
- **Depends on**: phase-3-2
- **合并后 main**: 启动预热钩子实现；LLM 重试可测

### Implementation Plan

#### Overview

性能与可靠性：重试、断路器、Embedding 预加载。

#### Tasks

- [ ] 1. [核心] `server/app/shared/resilience.py` — `retry_llm`、`CircuitBreaker`
- [ ] 2. [核心] `server/app/shared/llm.py` — 集成重试/断路器
- [ ] 3. [核心] `server/app/main.py` — `embedding_warmup()` 实现：启动加载 embedding 模型
- [ ] 4. [核心] `server/app/domain/rag/retriever.py` — 使用预加载模型句柄
- [ ] 5. [chore] Alembic — 整理迁移历史（squash 或文档说明，无破坏性变更）
- [ ] 6. [测试] `server/tests/unit/shared/test_resilience.py`

#### Verification

1. 冷启动后首次分析延迟低于未预热基线（手动记时）
2. `pytest server/tests/unit/shared/test_resilience.py` 通过

---

## PR: phase-5-3-deployment-docs

- **Branch**: `docs/deployment`
- **Depends on**: phase-0 ~ 4 基本完成
- **合并后 main**: 按文档从零机器可启动；生产 env 示例可审查

### Implementation Plan

#### Overview

本地排错与云上扩展文档；不交付真实云资源。

#### Tasks

- [ ] 1. [文档] `docs/deployment/local.md` — 端口、迁移、Chroma 首次下载 ~400MB、常见错误
- [ ] 2. [文档] `docs/deployment/cloud-database.md` — 托管 MySQL：`DATABASE_URL`、SSL、备份
- [ ] 3. [文档] `docs/deployment/cloud-frontend.md` — `npm run build`、CDN、`VITE_API_BASE_URL`、CORS
- [ ] 4. [文档] `server/.env.production.example`
- [ ] 5. [文档] `web/.env.production.example`
- [ ] 6. [文档] `README.md` — 链接 deployment 文档
- [ ] 7. [CI] `.github/workflows/deploy.yml` — **disabled** 模板 + 启用说明注释

#### Verification

1. 新环境按 `local.md` 从零启动成功
2. production example 无真实密钥，仅占位符

---

## 附录 A. AI 分析路由决策（Light / Medium / Heavy）

**流程**（Phase 3 `ExecutionPlanner`）：

```text
日记正文 → CrisisHandler? → Supervisor.classify() → execution_tier
                              ↓
                    light / medium / heavy executor
                              ↓
              失败时: heavy → medium → light → FALLBACK
```

### 意图 → 档位 → LLM 次数目标

| Intent | execution_tier | LLM 调用目标 | 执行器 |
|--------|----------------|--------------|--------|
| `pure_record` | `light` | ≤1 | `ai_executors/light.py` |
| `emotional_support` | `medium` | 2~3 | `ai_executors/medium.py` |
| `retrospective_review` | `heavy` | 4~6 | `ai_executors/heavy.py` |
| `habit_tracking` | `heavy` | 4~6 | `ai_executors/heavy.py` |
| 危机命中 | `light` + 安全模板 | 0~1 | `CrisisHandler`（图外） |

### 与 V1 差异

| V1 | V2 |
|----|-----|
| `chain` / `agent` / `multi_agent` 三模式用户选 | 用户不选；Supervisor + Skill 决定 tier |
| `agent.py` executor | **删除**；medium = 单 Worker |
| 硬编码 `DEFAULT_INTENT_ROUTING` | SkillRegistry 驱动 |

---

## 附录 B. V1 迁移对照速查

### 可原样迁移（评审后）

| V1 路径 | V2 目标 |
|---------|---------|
| `agents/intent_classifier.py` | `domain/agents/intent.py` |
| `agents/graph.py` | `domain/agents/graph.py` |
| `core/distributed_lock.py` | `infrastructure/distributed_lock.py` |
| `core/rate_limiter.py` | `infrastructure/rate_limiter.py` |
| `feedback/thompson_sampling.py` | `domain/feedback/thompson.py` |
| `memory/episodic.py`, `long_term.py` | `domain/memory/` |
| `skills/base.py`, `registry.py` + 10 implementations | `domain/skills/` |
| `frontend/.../useImplicitFeedback.ts` | `web/src/features/analysis/composables/` |

### 必须重写

| V1 文件 | V2 策略 |
|---------|---------|
| `services/ai_service.py` | `ai_router.py` + `ai_executors/{light,medium,heavy}.py` + `ai_prompts.py` + `ai_tools.py` |
| `services/vector_service.py` | `domain/rag/{chunker,bm25,retriever,reranker}.py` |
| `routers/admin.py` | `admin_service` + `api/v1/admin.py` |
| `routers/token_stats.py` | `token_stats_service` |
| `core/security.py` | `infrastructure/security.py` + 启动校验 |
| `pages/AdminPage.vue` | `features/admin/*` + 类型 |
| `pages/DiaryPage.vue` | composables + 子组件 |

### 删除不迁移

`_TEMPORAL_KEYWORDS`、`ai_service._fetch_weather_from_api()`、三 Agent 重复 Chroma 查询、PromptTuner 内重复 Thompson、empathy/crisis 重复情感关键词、`formatDate`/`formatTime` 前端重复、`err.response?.data?.detail` 重复处理。

---

## 执行顺序一览

| 顺序 | PR 章节 | Branch |
|------|---------|--------|
| 1 | phase-0-project-scaffold | `chore/project-scaffold` |
| 2 | phase-1-infrastructure-layer | `feature/infrastructure-layer` |
| 3 | phase-2-1-domain-knowledge | `feature/domain-knowledge` |
| 4 | phase-2-2-domain-rag | `feature/domain-rag` |
| 5 | phase-2-3-domain-memory | `feature/domain-memory` |
| 6 | phase-2-4-domain-feedback | `feature/domain-feedback` |
| 7 | phase-2-5-domain-skills | `feature/domain-skills` |
| 8 | phase-2-6-domain-agents | `feature/domain-agents` |
| 9 | phase-3-1-services-layer | `feature/services-layer` |
| 10 | phase-3-2-api-routes | `feature/api-routes` |
| 11 | phase-4-1-frontend-foundation | `feature/frontend-foundation` |
| 12 | phase-4-2-frontend-auth | `feature/frontend-auth` |
| 13 | phase-4-3-frontend-diary | `feature/frontend-diary` |
| 14 | phase-4-4-frontend-dashboard | `feature/frontend-dashboard` |
| 15 | phase-4-5-frontend-admin | `feature/frontend-admin` |
| 16 | phase-5-1-e2e-tests | `test/e2e-tests` |
| 17 | phase-5-2-perf-optimizations | `perf/optimizations` |
| 18 | phase-5-3-deployment-docs | `docs/deployment` |
