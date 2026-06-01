# Night Diary V2 — 任务总纲

> **仓库级施工蓝图**（非 Cursor Plan 文件）。每个 **PR = 下方一个章节**，含 `Implementation Plan` 三段式。
> **V1 只读参考**：`D:\work\night_diary`（不可修改）。**架构/协作细则**：`.cursor/rules/` 下 `architecture.mdc`、`collaboration.mdc`、`coding-standards.mdc`、`execution-plan.mdc`。

---

## 0. 如何使用本文

1. 按 **Phase 顺序**执行（A → E），每个 Phase 内 PR 按编号顺序合并。
2. 开始 PR 前：`git checkout main && git pull && git checkout -b <Branch>`（见各章节）。
3. 将对应章节的 **Tasks** 复制到 PR 描述（与 `.github/pull_request_template.md` 一致）。
4. **合并标准**：该 PR 的 Verification 全部通过，且 `main` 可运行（`make test` / `make lint` / 该阶段手动流）。
5. 当前应执行的 PR：见 `.cursor/rules/current_phase.mdc`（随进度更新）。

**累计 PR 数**：23（Phase A:5 + B:10 + C:3 + D:4 + E:1）

**架构方案**：`docs/本地化桌面端重构方案.md`（本文件仅维护施工清单，不重复论述设计决策）

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
| 架构约束 | 无 MySQL、无 Redis、无 JWT、无 Docker。单用户本地桌面应用。 |

---

## 2. 环境与启动策略

### 开发环境

```text
                                 npm run tauri dev
                                    │
  Vue 3 (Vite HMR)  ◄────────  Tauri v2 (Rust)  ──────────► Python sidecar
  http://localhost:5173                                        127.0.0.1:{port}
       (WebView)                                              (FastAPI, uvicorn)
                                                                  │
                                                          SQLite + ChromaDB
                                                      (%APPDATA%/night-diary/)
```

### 配置文件

| 配置方式 | 用途 |
|----------|------|
| CLI 参数 `--port` `--data-dir` | Tauri 启动 Python 时动态传入 |
| `server/.env` / 环境变量 | 本地开发时手动设置 |
| `%APPDATA%/night-diary/config.json` | 运行时非敏感配置（主题、窗口大小等） |
| `%APPDATA%/night-diary/secrets.key` | Fernet 密钥（加密 LLM API Key） |

### Makefile 目标

`make dev-api` / `make dev-web` / `make test` / `make lint`（与 CI 一致）

---

## PR: phase-a-1-server-adapt

- **Branch**: `refactor/desktop-architecture`
- **Depends on**: Phase 0 scaffold（`main`）
- **合并后 main**: `make dev-api` 启动 127.0.0.1:8000，`/health` 返回 200，`pytest` 通过，无 Docker 依赖

### Implementation Plan

#### Overview

服务端适配：config/main 移除 Redis/JWT/CORS，改为 SQLite + CLI 参数；删除 docker-compose；更新 CI。

#### Tasks

- [x] 1. [核心] `server/app/config.py` — 移除 `redis_url`/`jwt_*`/`allowed_origins`/`trusted_proxy_ips`；新增 `data_dir`/`port`；`database_url` 等改为 `@property` 派生自 `data_dir`；`model_key_secret` 改为可选
- [x] 2. [核心] `server/app/main.py` — 移除 CORS；新增 `--port`/`--data-dir` CLI 参数；`create_app()` 内自动创建数据目录；新增 `/shutdown` 端点
- [x] 3. [核心] `server/pyproject.toml` — 移除 `redis`/`pymysql`/`cryptography`/`types-redis`；新增 `aiosqlite`
- [x] 4. [核心] `server/.env.example` — 精简为 `APP_ENV`/`DATA_DIR`/`PORT`/`MODEL_KEY_SECRET`/`LLM_*`
- [x] 5. [核心] 删除 `docker-compose.yml`；简化 `Makefile`（去 Docker 目标）；更新 `.github/workflows/ci.yml`（去 Redis/JWT env vars）
- [x] 6. [测试] 更新 `tests/conftest.py`/`test_config.py` — 适配新 Settings
- [x] 7. [文档] 新增 `docs/本地化桌面端重构方案.md`；更新 `README.md` 和 `.cursor/rules/`

#### Verification

1. `make dev-api` 启动成功，`curl localhost:8000/health` → 200
2. `make test` — pytest 5 passed
3. `make lint` — ruff + mypy 全部通过
4. CI 全绿，无 Docker 服务依赖

---

## PR: phase-a-2-tauri-shell

- **Branch**: `feature/tauri-shell`
- **Depends on**: phase-a-1（server-adapt）
- **合并后 main**: `npm run tauri dev` 打开桌面窗口；启动画面显示；Python sidecar 自动启动

### Implementation Plan

#### Overview

初始化 Tauri v2 项目脚手架：Rust 源码、窗口配置、启动画面、Vite 集成。

#### Tasks

- [ ] 1. [核心] 安装 Tauri CLI：`npm install -D @tauri-apps/cli@latest`；`npm run tauri init`，生成 `src-tauri/`
- [ ] 2. [核心] `src-tauri/Cargo.toml` — 依赖 `tauri` v2、`tauri-plugin-shell`、`tokio`、`serde`、`serde_json`
- [ ] 3. [核心] `src-tauri/tauri.conf.json` — 窗口标题 "夜记"、无边框（`decorations: false`）、最小尺寸 900×600、默认 1200×800；identifier `com.nightdiary.app`
- [ ] 4. [核心] `src-tauri/resources/splash.html` — 启动画面：Logo 居中 + "正在准备 AI 引擎..." + 进度条动画
- [ ] 5. [核心] `src-tauri/src/main.rs` — 入口：加载 splash → 启动 Python sidecar → 健康检查 → 关闭 splash → 打开主窗口
- [ ] 6. [核心] `src-tauri/src/lib.rs` — Tauri commands：`get_backend_port()`、`get_data_dir()`、`get_app_version()`
- [ ] 7. [核心] `src-tauri/src/process.rs` — Python 子进程管理：`spawn_backend()`、`health_poll()`、`graceful_shutdown()`
- [ ] 8. [核心] `src-tauri/capabilities/default.json` — Tauri v2 权限声明（shell 执行、窗口管理）
- [ ] 9. [核心] `src-tauri/icons/` — 应用图标（ico + png）
- [ ] 10. [配置] 更新 `package.json` scripts — `tauri dev`、`tauri build`
- [ ] 11. [配置] 更新 `vite.config.ts` — Tauri 适配（`server.strictPort = true`）

#### Verification

1. `npm run tauri dev` 打开桌面窗口
2. 启动画面短暂显示后自动切换到 Vue 页面
3. Python 进程随窗口关闭自动退出
4. `make lint-web` 通过（vue-tsc + eslint）

---

## PR: phase-a-3-frontend-migration

- **Branch**: `feature/frontend-migration`
- **Depends on**: phase-a-2（tauri-shell）
- **合并后 main**: `web/` → `src/` 迁移完成；Vue 通过 Tauri invoke 获取后端端口；API 请求正确发往 Python sidecar

### Implementation Plan

#### Overview

将 `web/` 目录迁移为 `src/`（Tauri 前端标准布局），建立 Vue-Tauri 通信桥接。

#### Tasks

- [ ] 1. [核心] 移动 `web/` 所有文件到 `src/`（保留 `web/` 为兼容期软链接或直接删除）
- [ ] 2. [核心] 更新 `vite.config.ts` — 根目录改为 `./`，`@` alias 保持指向 `src/`
- [ ] 3. [核心] 更新 `index.html` — 位于项目根目录
- [ ] 4. [核心] `src/shared/api/http.ts` — 新增 `useBackend()` composable：通过 `invoke('get_backend_port')` 获取端口，动态设置 axios `baseURL`
- [ ] 5. [核心] `src/App.vue` — 改造为 Tauri 感知：启动时等待后端端口就绪，显示加载状态
- [ ] 6. [配置] 更新 `Makefile` — `dev-web` 目标指向 `npm run tauri dev`
- [ ] 7. [配置] 更新 CI — web job 的 `working-directory` 仍为 `web/` 或更新为根目录
- [ ] 8. [清理] 删除 `web/` 目录中已迁移的冗余文件

#### Verification

1. `npm run tauri dev` → 桌面窗口打开，Vue 页面正确渲染
2. `curl` 验证前端 API 请求正确到达 Python 后端
3. `make test-web` — vitest 通过
4. `make lint-web` — vue-tsc + eslint 通过

---

## PR: phase-a-4-frontend-cleanup

- **Branch**: `chore/frontend-cleanup`
- **Depends on**: phase-a-3（frontend-migration）
- **合并后 main**: `web/` 目录完全删除；前端目录结构为 `src/` 标准 Tauri 布局

### Implementation Plan

#### Overview

删除旧 `web/` 目录，验证构建链路完整。

#### Tasks

- [ ] 1. [清理] 删除 `web/` 目录
- [ ] 2. [配置] 验证 `package.json`、`vite.config.ts`、`tsconfig.json` 路径均指向 `src/`
- [ ] 3. [配置] 更新 CI — web job 的 working-directory 改为根目录
- [ ] 4. [配置] 更新 `.gitignore` — 移除 `web/` 专属忽略规则
- [ ] 5. [文档] 更新 `README.md` 目录结构图

#### Verification

1. `npm install && npm run tauri dev` 从零构建成功
2. `make test` / `make lint` 全部通过
3. CI 全绿

---

## PR: phase-a-5-python-build

- **Branch**: `feature/python-pyinstaller`
- **Depends on**: phase-a-4（frontend-cleanup）
- **合并后 main**: `server/build.spec` 可用；`pyinstaller server/build.spec` 生成独立 Python .exe

### Implementation Plan

#### Overview

为 Python AI 引擎编写 PyInstaller spec，确保 ChromaDB/onnxruntime/torch 等原生依赖正确打包。

#### Tasks

- [ ] 1. [核心] `server/build.spec` — PyInstaller spec 文件：hidden imports（chromadb、onnxruntime、sentence_transformers、jieba、torch、tokenizers）
- [ ] 2. [核心] 处理二进制依赖 — ChromaDB 的 onnxruntime DLL、sentence-transformers 的模型文件路径
- [ ] 3. [核心] `server/app/main.py` 的 `main()` 函数 — 确保 PyInstaller 入口正确
- [ ] 4. [文档] `server/README.md` 或 `docs/` — 打包说明（命令、常见问题）

#### Verification

1. `pyinstaller server/build.spec` 成功生成 `dist/nightdiary-backend.exe`
2. 手动运行生成的 .exe：`nightdiary-backend.exe --port 8000 --data-dir ./testdata`
3. `curl localhost:8000/health` → 200

---

## PR: phase-b-1-domain-knowledge

- **Branch**: `feature/domain-knowledge`
- **Depends on**: Phase A 全部完成
- **合并后 main**: `DomainKnowledgeStore` 作为 ChromaDB 唯一查询入口可单元测试

### Implementation Plan

#### Overview

迁移 V1 `domain_store.py` + `extractor.py` → `server/app/domain/knowledge/`。修复 V1 坏味 3（重复查询逻辑）：所有 Agent 通过此类查询领域知识。

#### Tasks

- [ ] 1. [核心] `server/app/domain/knowledge/types.py` — `KnowledgeHit`、`EntityRecord` dataclass/TypedDict
- [ ] 2. [核心] `server/app/domain/knowledge/store.py` — `DomainKnowledgeStore`：迁移 V1 `domain_store.py`；`query()`/`add()`/`delete()`；读 `Settings.chroma_persist_dir`；单例 Chroma client
- [ ] 3. [核心] `server/app/domain/knowledge/extractor.py` — 迁移 V1 extractor；修复 `entity_type` 文档与实现不一致
- [ ] 4. [测试] `tests/unit/domain/knowledge/test_store.py` — mock Chroma client
- [ ] 5. [测试] `tests/unit/domain/knowledge/test_extractor.py`
- [ ] 6. [可观测性] `DomainKnowledgeStore.query()` 记录检索 trace（query_text, hit_count, top_score, latency_ms）

#### Verification

1. `pytest server/tests/unit/domain/knowledge -v` 通过
2. 无模块级 `load_dotenv()`；配置仅来自 `config.py`
3. 检索调用有 trace 日志（query_text + hit_count + latency_ms）

---

## PR: phase-b-2-rag-foundation

- **Branch**: `feature/rag-foundation`
- **Depends on**: phase-b-1（domain-knowledge）
- **合并后 main**: RAG 基础组件（chunker/bm25/collections）可单元测试

### Implementation Plan

#### Overview

从 V1 `vector_service.py`（771 行）拆分出**基础零件**层：`ChunkSplitter` + `BM25Index`（含增量更新）+ `DiaryCollectionManager`。这三个模块不涉及检索编排，只负责各自的核心功能。**BM25 增量算法为 V1 没有的新功能**，需独立实现和验证。

> 注意：原 task.md 的 `phase-b-2-domain-rag` 已被拆分为 B-2（本 PR）+ B-3（rag-retrieval）。原因：拆分 770 行 God class（重构）与实现 BM25 增量算法（新功能）是两类工作，应分开 review。

#### Tasks

- [ ] 1. [核心] `server/app/domain/rag/types.py` — `Chunk`、`BM25Doc`、`SearchResult` 数据类
- [ ] 2. [核心] `server/app/domain/rag/chunker.py` — `ChunkSplitter`；合并 V1 `ParentChildChunker` 逻辑
- [ ] 3. [核心] `server/app/domain/rag/bm25.py` — `BM25Index` **类实例**（非模块级 dict）；支持增量 `add_document()` / `remove_document()`；`tokenize` + `df` + `avgdl` 增量维护，不每次全量重建
- [ ] 4. [核心] `server/app/domain/rag/collections.py` — `DiaryCollectionManager`：日记 chunk 的 collection 生命周期（创建、更新、删除）
- [ ] 5. [测试] `tests/unit/domain/rag/` — test_chunker / test_bm25 / test_collections
- [ ] 6. [性能] BM25 `add_document()` 增量更新计时验证：O(1) 而非 O(n)

#### Verification

1. `pytest server/tests/unit/domain/rag/test_chunker test_bm25 test_collections -v` 通过
2. BM25 新增 1 条文档后计时 < 10ms（对比全量重建 O(n) 随文档数线性增长）
3. 无模块级副作用（`BM25Index` 以类实例存在，非模块级 dict）

---

## PR: phase-b-3-rag-retrieval

- **Branch**: `feature/rag-retrieval`
- **Depends on**: phase-b-2（rag-foundation）
- **合并后 main**: `HybridRetriever` + `Reranker` 可单元测试（mock embedding）

### Implementation Plan

#### Overview

在 B-2 基础零件之上，实现检索编排层：`HybridRetriever`（向量 + BM25 融合）+ `Reranker`（带降级）。消除 V1 的 `os.environ` 全局写入（坏味 3）。

#### Tasks

- [ ] 1. [核心] `server/app/domain/rag/retriever.py` — `HybridRetriever`：向量 + BM25 融合；依赖 B-1 `DomainKnowledgeStore` + B-2 `BM25Index`
- [ ] 2. [核心] `server/app/domain/rag/reranker.py` — `Reranker`：懒加载模型（首次调用时加载）；**实例级**配置，禁止 `os.environ` 全局写入；加载失败时 `fallback()` 返回原始融合结果
- [ ] 3. [可观测性] `HybridRetriever.retrieve()` 记录混合检索 trace（vector_results_count, bm25_results_count, fused_results_count, latency_ms）
- [ ] 4. [测试] `tests/unit/domain/rag/` — test_retriever / test_reranker
- [ ] 5. [韧性] Reranker 降级测试：模拟模型加载失败，验证返回原始结果且不抛异常

#### Verification

1. `pytest server/tests/unit/domain/rag/test_retriever test_reranker -v` 通过
2. 无模块级副作用（如 `HF_HUB_OFFLINE=1` 全局 env 写入）
3. 混合检索有 trace 日志（各阶段结果数 + 延迟）
4. Reranker 加载失败时降级，不抛异常

---

## PR: phase-b-4-domain-memory

- **Branch**: `feature/domain-memory`
- **Depends on**: phase-b-3（rag-retrieval）
- **合并后 main**: 三层记忆系统可用（进程内存储，无 Redis）；Episodic Memory 默认持久化

### Implementation Plan

#### Overview

迁移 V1 记忆系统。Episodic Memory 从 Redis Sorted Set 改为进程内 `deque` + SQLite 持久化（默认开启）。Long-Term Memory 从 MySQL JSON 改为 SQLite JSON 列。Working Memory 实际集成到 Multi-Agent 流程。

> 持久化决策：V2 为单用户桌面应用，关闭窗口即进程销毁。若 Episodic Memory 不做持久化，用户每次重启应用将丢失全部短期记忆——这与「AI 心理陪伴」的产品定位冲突。存储成本约 50KB，不构成 trade-off，故**默认开启**。

#### Tasks

- [ ] 1. [核心] `server/app/domain/memory/types.py` — `EpisodicEntry`、`UserProfile`、`WorkingContext` dataclass/TypedDict
- [ ] 2. [核心] `server/app/domain/memory/episodic.py` — `EpisodicMemory` 类：基于 `deque[EpisodicEntry]`，max 100 条，LRU 淘汰，重要性分数过滤（> 0.5），7 天半衰期时间衰减；**SQLite 持久化默认开启**（启动时 `load()`，写入时 `upsert()`）
- [ ] 3. [核心] `server/app/domain/memory/long_term.py` — `LongTermMemory` 类：SQLite JSON 存储 `UserProfile`，情绪/话题跨天检测（连续 3+ 天 → 提升到长期档案）
- [ ] 4. [核心] `server/app/domain/memory/working.py` — `WorkingMemory` 类：包装 MultiAgentState，4000 token 限制（**必须集成到 ai_service 中**，V1 中是死代码）
- [ ] 5. [测试] `tests/unit/domain/memory/` — test_episodic（含持久化读写）/ test_long_term / test_working

#### Verification

1. `pytest server/tests/unit/domain/memory -v` 通过
2. Episodic 写入 + 读取 + 淘汰流程正确；不依赖 Redis
3. Episodic 持久化：写入 → 模拟重启（新建实例 → load） → 验证记忆恢复
4. 7 天半衰期：验证过期条目 score 衰减至 < 0.5 后被淘汰

---

## PR: phase-b-5-domain-feedback

- **Branch**: `feature/domain-feedback`
- **Depends on**: phase-b-4（domain-memory）
- **合并后 main**: Thompson Sampling + PromptTuner 可单元测试

### Implementation Plan

#### Overview

迁移 V1 feedback 模块。消除 V1 坏味 3：PromptTuner 调用 ThompsonSampling 而非重新实现 Beta 采样。

#### Tasks

- [ ] 1. [核心] `server/app/domain/feedback/thompson_sampling.py` — 迁移 V1 `thompson_sampling.py`；四种风格（共情/务实/哲思/幽默）
- [ ] 2. [核心] `server/app/domain/feedback/prompt_tuner.py` — 迁移 V1 `prompt_tuner.py`；删除重复的 `_sample_style_from_preferences()`（调用 `ThompsonSampling.sample_style()`）；`_infer_response_length()` stub 完成实现（接收日记字数、时间、情绪强度作为输入，留扩展接口供 B-9 Agent 层传入）
- [ ] 3. [测试] `tests/unit/domain/feedback/` — test_thompson_sampling / test_prompt_tuner
- [ ] 4. [测试] `tests/unit/domain/feedback/test_thompson_distribution.py` — N=1000 统计测试，chi-square 检验验证四种风格分布符合 Beta 参数（`random.seed(42)` 确保可复现）

#### Verification

1. `pytest server/tests/unit/domain/feedback -v` 通过
2. `PromptTuner._sample_style_from_preferences()` 调用 `ThompsonSampling.sample_style()` 而非自行实现
3. Thompson Sampling 统计测试通过（N=1000，chi-square p > 0.05）

---

## PR: phase-b-6-skills-migration

- **Branch**: `feature/skills-migration`
- **Depends on**: phase-b-5（domain-feedback）
- **合并后 main**: Skill 系统就位（独立可测，MVP: crisis_detector + sentiment_skill 激活；其余 8 个 stub）

### Implementation Plan

#### Overview

迁移 V1 10 个 Skill + SkillRegistry。V1 的 skills 模块是**死代码**（坏味 2），从未在生产中运行。为降低风险，本 PR 以 MVP 策略交付：只激活 `crisis_detector`（安全关键）和 `sentiment_skill`（核心能力），其余 8 个 Skill 保留为 stub（`can_activate()` 返回 `False`），后续逐个 mini-PR 激活并跑 `make eval` 验证质量。

> **重要**：本 PR **不包含** Supervisor 集成。Skill 可独立通过 mock 输入验证 `select_skills()` 输出。Supervisor 集成推迟到 B-9（Supervisor 已就位后），避免前向依赖。

#### Tasks

- [ ] 1. [核心] `server/app/domain/skills/base.py` — `BaseSkill` 抽象类 + `SkillMetadata`（name, description, triggers, priority）
- [ ] 2. [核心] `server/app/domain/skills/registry.py` — `SkillRegistry` 贪心选择算法（激活阈值 0.3）；`select_skills(text, profile)` 遍历全部 Skill，返回激活列表
- [ ] 3. [核心] `server/app/domain/skills/crisis_detector.py` — **MVP 激活**：极端负面情绪关键词 + 情绪分数阈值 → 激活安全干预
- [ ] 4. [核心] `server/app/domain/skills/sentiment_skill.py` — **MVP 激活**：情绪极性 + 强度检测
- [ ] 5. [核心] 其余 8 个 Skill stub — 完整类结构 + `can_activate()` 返回 `False` + `execute()` 标记 `NotImplementedError`；后续按以下批次逐个激活：
  - `pattern_detector` / `habit_tracker`（模式识别，需 ≥3 条日记）
  - `memory_reader` / `memory_writer`（长期记忆读写）
  - `summary_generator` / `search_diary_skill`（生成与检索）
  - `weather_skill` / `address_skill`（外部信息增强）
- [ ] 6. [测试] `tests/unit/domain/skills/` — test_registry / test_crisis_detector / test_sentiment_skill
- [ ] 7. [可观测性] `server/app/infrastructure/tracer.py` 中定义 `SkillActivationTracer` — 记录每次 `can_activate()` 的调用（skill_name, score, threshold, activated, reason），为 B-9 写入 `skill_activations` 表做准备

#### Verification

1. `pytest server/tests/unit/domain/skills -v` 通过
2. `SkillRegistry.select_skills()` 在单元测试中有调用点（不再是死代码）
3. crisis_detector 对明显危机文本（"我不想活了"）返回激活，对普通文本不激活
4. 8 个 stub Skill 在 registry 中注册但不激活

---

## PR: phase-b-7-agents-shared

- **Branch**: `feature/agents-shared`
- **Depends on**: phase-b-6（skills-migration）
- **合并后 main**: Agent 共享基础设施就位（EmotionEstimator / TokenEstimator / MultiAgentState / LLMCallTracer）

### Implementation Plan

#### Overview

从原 B-6 中提取所有 Agent 的**共同依赖**，前置交付。这些模块原本散落在原 B-6 的 20 个 task 中，先集中定义接口和实现，后续 B-8/B-9 直接注入使用，不再回改。

> 拆分原因：原 B-6（20 tasks）混合了共享工具、3 个 Worker Agent、Supervisor 编排、韧性测试四类工作。一个 PR 承载不了这么多。

#### Tasks

- [ ] 1. [核心] `server/app/shared/emotion_estimator.py` — `EmotionEstimator` 类：统一的情感估计接口（消除 V1 坏味 3：empathy_agent 和 crisis_detector 的重复实现）
- [ ] 2. [核心] `server/app/shared/token_utils.py` — `estimate_tokens()`：统一的 token 估算（消除 V1 坏味 3：retrieval_agent 和 context_compressor 的重复实现）
- [ ] 3. [核心] `server/app/domain/agents/state.py` — `MultiAgentState` TypedDict + reducer
- [ ] 4. [核心] `server/app/infrastructure/tracer.py` — `LLMCallTracer`：Agent 通过 DI 接收，每次 LLM 调用写入 `llm_call_logs` 表
- [ ] 5. [核心] `server/app/infrastructure/models/` — SQLite ORM 定义：`llm_call_logs`、`agent_decisions`（含 `skill_ids` JSON 列）、`skill_activations` 三张表
- [ ] 6. [测试] `tests/unit/shared/` — test_emotion_estimator / test_token_utils
- [ ] 7. [可观测性] 建表 SQL：`skill_activations` 表结构（skill_name, activated, score, threshold, input_digest, reason, latency_ms, decision_id FK）

#### Verification

1. `pytest server/tests/unit/shared -v` 通过
2. `EmotionEstimator` 与 `estimate_tokens()` 在 `shared/` 中有唯一定义（不在 Agent 中重复实现）
3. `llm_call_logs` / `agent_decisions` / `skill_activations` 三张表的 ORM 模型可通过 SQLite 创建

---

## PR: phase-b-8-agents-workers

- **Branch**: `feature/agents-workers`
- **Depends on**: phase-b-7（agents-shared）+ B-1~B-5（全部领域模块）
- **合并后 main**: 3 个 Worker Agent + IntentClassifier 可独立单元测试（mock LLM）

### Implementation Plan

#### Overview

迁移 V1 的 3 个 Worker Agent（Empathy / Retrieval / Insight）+ IntentClassifier。全部通过 DI 接收 LLM / DB session / KnowledgeStore / EmotionEstimator / TokenEstimator / Tracer。每个 Agent 实现 `fallback()` 方法。

#### Tasks

- [ ] 1. [核心] `server/app/domain/agents/intent_classifier.py` — 迁移 V1（两级分类，设计最干净的模块，基本不变）
- [ ] 2. [核心] `server/app/domain/agents/empathy_agent.py` — 迁移 V1；通过 DI 接收 LLM；共享 `DomainKnowledgeStore`/`EmotionEstimator`/`TokenEstimator`/`LLMCallTracer`；删除自行创建 `SessionLocal()`/`ChatOpenAI()`
- [ ] 3. [核心] `server/app/domain/agents/retrieval_agent.py` — 迁移 V1；多跳检索（最多 3 次）；时间范围推断；共享 `DomainKnowledgeStore`；锚定机制：每轮 query 与原始 query 语义相似度 < 0.3 时停止
- [ ] 4. [核心] `server/app/domain/agents/insight_agent.py` — 迁移 V1；支持常规分析 + 周报/月报；DI 改造
- [ ] 5. [韧性] 每个 Worker Agent 实现 `fallback()` 方法：LLM 超时/不可用时返回预设安全回复（EmpathyAgent → 共情模板；RetrievalAgent → 空上下文标记；InsightAgent → "暂时无法生成分析"）
- [ ] 6. [测试] `tests/unit/domain/agents/` — test_intent_classifier / test_empathy_agent / test_retrieval_agent / test_insight_agent（全部 mock LLM）
- [ ] 7. [测试] Agent fallback 测试：模拟 LLM API 不可达，验证各 Worker 返回 `fallback()` 安全回复，管线不崩溃
- [ ] 8. [可观测性] Agent 调用 LLM 时通过 DI 的 `LLMCallTracer` 写入 `llm_call_logs`

#### Verification

1. `pytest server/tests/unit/domain/agents/test_intent test_empathy test_retrieval test_insight -v` 通过
2. Agent 不自行创建 `SessionLocal()` 或 `ChatOpenAI()`——全部通过 DI 接收
3. 3 个 Worker Agent 共享 `DomainKnowledgeStore`/`EmotionEstimator`/`TokenEstimator`
4. 每次 LLM 调用有 trace 记录（`llm_call_logs` 表有对应行）
5. LLM API 不可达时各 Agent 返回 fallback，不抛异常

---

## PR: phase-b-9-agents-orchestration

- **Branch**: `feature/agents-orchestration`
- **Depends on**: phase-b-8（agents-workers）+ phase-b-6（skills-migration）
- **合并后 main**: Supervisor + Graph 编排就位；Skill 正式集成到 Agent 管线

### Implementation Plan

#### Overview

迁移 Supervisor + Graph 编排层，并将 B-6 迁移的 Skill 系统**正式集成**到 Agent 管线中。Supervisor 调用 `SkillRegistry.select_skills()` 替代硬编码路由；所有决策记录到 `agent_decisions` + `skill_activations` 表。

#### Tasks

- [ ] 1. [核心] `server/app/domain/agents/supervisor.py` — `SupervisorAgent`：classify → activate skills → allocate budget → route → synthesize
- [ ] 2. [核心] **Skill 集成**：`classify_intent()` 中调用 `SkillRegistry.select_skills()`；激活的 skill 列表写入 `agent_decisions.skill_ids`
- [ ] 3. [核心] **Skill 追踪**：每次 `can_activate()` 调用写入 `skill_activations` 表（激活+抑制全部记录）
- [ ] 4. [核心] `server/app/domain/agents/graph.py` — `MultiAgentGraphBuilder`：条件路由（根据 tier）、parallel fan-out（`asyncio.gather` + `return_exceptions=True`）、安全 Worker 包装
- [ ] 5. [韧性] Supervisor 合成时容忍部分 Worker 失败：单个 Worker 超时/失败 → 用剩余 Worker 结果降级合成（不抛异常）
- [ ] 6. [可观测性] Supervisor 决策记录到 `AgentDecisionLogger`（intent_classification, tier_routing, skill_activation, worker_routing）
- [ ] 7. [测试] `tests/unit/domain/agents/` — test_supervisor / test_graph（mock 全部 Worker + mock SkillRegistry）
- [ ] 8. [测试] Worker 超时降级测试：模拟单个 Worker 超时（`asyncio.wait_for` timeout）→ 验证 Supervisor 降级合成剩余结果

#### Verification

1. `pytest server/tests/unit/domain/agents/test_supervisor test_graph -v` 通过
2. `SkillRegistry.select_skills()` 在生产代码中有调用点（Supervisor.classify_intent）
3. `agent_decisions` 表含 skill_ids 字段（JSON array）
4. `skill_activations` 表记录完整（每次 can_activate 调用，含激活和抑制）
5. Supervisor 决策路径可追溯（intent + tier + skills + routing）
6. Worker 超时降级测试通过：单个 Worker 超时 → 用剩余结果合成，不抛异常

---

## PR: phase-b-10-agents-resilience

- **Branch**: `feature/agents-resilience`
- **Depends on**: phase-b-9（agents-orchestration）
- **合并后 main**: Context Compressor 集成 + 韧性测试体系完整 + Eval 基线建立

### Implementation Plan

#### Overview

Phase B 的最后一块拼图。集成 Context Compressor、建立完整的降级测试体系、追加 Eval 用例。本 PR 不引入新的 Agent 逻辑——专注在「已有管线在异常条件下的行为正确性」。

#### Tasks

- [ ] 1. [核心] `server/app/domain/agents/context_compressor.py` — 迁移 V1，**实际集成**到 multi_agent 流程：在 WorkingMemory 4000 token 窗口内，用语义相似度选择性保留相关上下文，压缩至 ~1500 token
- [ ] 2. [测试] 多跳检索漂移测试：构造首轮检索返回不相关结果的场景 → 验证 RetrievalAgent 锚定机制生效，第二轮不无限漂移
- [ ] 3. [测试] Context Compressor 正确性测试：验证压缩后上下文保留 query 相关部分，丢弃无关部分
- [ ] 4. [测试] Eval 用例：追加 5 条日记输入 + 结构化评判标准到 `tests/eval/test_cases.json`
- [ ] 5. [文档] 更新 `README.md` / `.cursor/rules/current_phase.mdc` — 标记 Phase B 完成

#### Verification

1. `pytest server/tests/unit/domain/agents/test_context_compressor -v` 通过
2. 多跳检索漂移测试通过（锚定机制生效）
3. 改 prompt 后 `make eval` 不退化（评分无明显下降）
4. Phase B 全部 10 个 PR 合并后 `main` 可运行（`make test` + `make lint` 通过）

## PR: phase-c-1-services-layer

- **Branch**: `feature/services-layer`
- **Depends on**: Phase B 全部完成
- **合并后 main**: 服务层就位，AI 分析端到端可调用

### Implementation Plan

#### Overview

实现服务层：diary CRUD、analysis 编排、AI 执行路由（三级：light/medium/heavy）。拆分 V1 的 `ai_service.py`（987 行 God class）。

#### Tasks

- [ ] 1. [核心] `server/app/services/__init__.py`
- [ ] 2. [核心] `server/app/services/diary_service.py` — 日记 CRUD；创建/更新时同步向量库（调用 `DiaryCollectionManager`）；不再有 `user_id` 参数
- [ ] 3. [核心] `server/app/services/analysis_service.py` — 编排：条目所有权检查 → 7 天历史查询 → AI router 调用 → 结果存储。消除重复 7 天逻辑（V1 坏味 3）
- [ ] 4. [核心] `server/app/services/ai/` — 从 V1 拆分为：
  - `router.py` — `ExecutionPlanner`：light/medium/heavy 路由决策（~80 行）
  - `prompts.py` — System Prompt 模板（~80 行）
  - `tool_factory.py` — 工具工厂函数（~200 行）
  - `chain_executor.py` — chain 模式（~40 行）
  - `agent_executor.py` — ReAct Agent 模式（~100 行）
  - `multi_agent_executor.py` — Multi-Agent 模式，调用 WorkingMemory（~150 行）
  - `utils.py` — 缓存判断、结果过滤、Token 提取（~60 行）
- [ ] 5. [核心] `server/app/services/feedback_service.py` — 反馈写入 + 异步更新 Thompson Sampling
- [ ] 6. [核心] `server/app/services/tag_service.py` — 标签 CRUD
- [ ] 7. [核心] `server/app/services/model_service.py` — LLM 提供商 CRUD + Fernet 加密 API Key
- [ ] 8. [测试] `tests/unit/services/` — test_diary_service / test_analysis_service / test_ai_router
- [ ] 9. [可观测性] `ExecutionPlanner` 记录路由决策 trace（diary_length, detected_intent, selected_tier, activated_skills, estimated_tokens）— 写入 `agent_decisions` 表
- [ ] 10. [性能] `ExecutionPlanner` 支持 per-tier model selection：用户可为 light/medium/heavy 分别配置不同 LLM model（读取 `ModelProvider.tier` 字段）

#### Verification

1. `pytest server/tests/unit/services -v` 通过
2. `ai_service` 不再是一个 1000 行的文件——拆分为 `ai/` 目录下的 7 个模块
3. 不同 tier 的路由决策有 trace 日志（通过 `AgentDecisionLogger`）
4. 为不同 tier 配置不同 LLM model 后，验证实际使用了对应模型（通过 `llm_call_logs.model` 字段）

---

## PR: phase-c-2-api-routes

- **Branch**: `feature/api-routes`
- **Depends on**: phase-c-1（services-layer）
- **合并后 main**: API 路由全部就位，`/docs` 可查看完整 Swagger

### Implementation Plan

#### Overview

实现所有 API 路由。路由层仅负责认证（无，单用户）→ 参数提取 → 调用 service → 格式化响应。使用 `AppError` 子类替代字符串匹配（V1 坏味 4）。

#### Tasks

- [ ] 1. [核心] `server/app/api/v1/__init__.py` + `router.py` — 注册所有子路由
- [ ] 2. [核心] `server/app/api/v1/diary.py` — 5 个端点（list/create/get/update/delete）
- [ ] 3. [核心] `server/app/api/v1/analysis.py` — 2 个端点（trigger/get）
- [ ] 4. [核心] `server/app/api/v1/feedback.py` — 1 个端点（submit 👍/👎）
- [ ] 5. [核心] `server/app/api/v1/tags.py` — 3 个端点（list/create/delete）
- [ ] 6. [核心] `server/app/api/v1/models.py` — 4 个端点（list/create/update/delete）— LLM 配置管理
- [ ] 7. [核心] `server/app/api/v1/stats.py` — 1 个端点（日记数、Token 用量等统计）
- [ ] 8. [核心] `server/app/shared/errors.py` — `AppError` 基类 + `DiaryError`/`AnalysisError`/`ValidationError` 子类 + `http_status` 映射
- [ ] 9. [核心] `server/app/api/v1/error_handlers.py` — FastAPI exception handlers：`AppError` → HTTP 状态码映射
- [ ] 10. [测试] `tests/unit/api/` — test_diary_routes / test_analysis_routes

#### Verification

1. `pytest server/tests/unit/api -v` 通过
2. `make dev-api` 后访问 `http://127.0.0.1:8000/docs` 查看完整 Swagger
3. 所有路由层代码不包含业务逻辑——仅参数提取 + service 调用 + 响应格式化

---

## PR: phase-c-3-llm-management

- **Branch**: `feature/llm-management`
- **Depends on**: phase-c-2（api-routes）
- **合并后 main**: 用户可通过 Settings 页面配置 LLM 提供商

### Implementation Plan

#### Overview

LLM 配置管理：ModelProvider CRUD + Fernet 加密 + LLMFactory。统一所有 Agent 使用用户配置的 LLM（V1 坏味 3）。

#### Tasks

- [ ] 1. [核心] `server/app/shared/llm.py` — `LLMFactory.create(provider, settings)`：支持用户配置的 `ModelProvider`；兼容 OpenAI API 格式
- [ ] 2. [核心] `server/app/infrastructure/security.py` — Fernet 加解密：`encrypt_api_key()`/`decrypt_api_key()`；密钥从 `Settings.model_key_secret` 或 `secrets.key` 文件
- [ ] 3. [核心] 更新 `model_service.py` — API Key 存储前加密，读取时解密，API 响应绝不返回原始密钥
- [ ] 4. [配置] `ModelProvider` 支持 `tier` 字段（light/medium/heavy/default），允许 per-tier 模型选择；`LLMFactory.create(tier)` 按 tier 查找对应模型
- [ ] 5. [配置] 前端 Settings 场景：LLM 配置表单（base_url / api_key / model_name / tier / 设为默认）
- [ ] 6. [测试] `tests/unit/test_llm.py` — LLMFactory + 加解密 + per-tier 模型查找

#### Verification

1. `pytest server/tests/unit/test_llm -v` 通过
2. 数据库中的 `api_key_encrypted` 字段为密文
3. API 响应不包含原始 API Key
4. 为不同 tier 配置不同模型后，`LLMFactory.create(tier="heavy")` 返回正确模型

---

## PR: phase-d-1-design-system

- **Branch**: `feature/design-system`
- **Depends on**: Phase C 全部完成
- **合并后 main**: 游戏化 UI 设计系统就位，Storybook 或临时 demo 页面可预览所有组件

### Implementation Plan

#### Overview

构建游戏化 UI 组件库：玻璃态面板、动画按钮、粒子背景、页面过渡动画。

#### Tasks

- [ ] 1. [核心] `src/shared/components/GlassPanel.vue` — 毛玻璃容器：`backdrop-blur-xl bg-white/10 dark:bg-black/20 border border-white/20 rounded-2xl shadow-2xl`
- [ ] 2. [核心] `src/shared/components/GameButton.vue` — 动画按钮：hover 微放大 + 阴影提升；click 微缩小 + 涟漪；variants（primary/secondary/ghost）
- [ ] 3. [核心] `src/shared/components/ParticleBackground.vue` — Canvas 粒子系统：日间暖色浮尘；夜间星空视差；主题切换平滑过渡
- [ ] 4. [核心] `src/shared/components/PageTransition.vue` — Vue `<Transition>` 包装：当前页 fade-out + scale-down；下一页 fade-in + scale-up
- [ ] 5. [核心] `src/shared/components/AITypingIndicator.vue` — 三个脉动光点 + "正在思考..." 标签
- [ ] 6. [核心] `src/shared/components/MoodSelector.vue` — 情绪 emoji 网格（非下拉框）：hover 光晕 + 选中弹跳动画
- [ ] 7. [核心] `src/shared/components/CustomTitlebar.vue` — 自定义标题栏：可拖拽区域 + 窗口控制按钮（最小化/最大化/关闭）
- [ ] 8. [样式] `src/styles/base.css` — Tailwind base + CSS 变量（`--color-primary`、`--glass-bg` 等）
- [ ] 9. [样式] `src/styles/themes/day.css` + `night.css` — 日间暖色系 / 夜间深色星空系
- [ ] 10. [样式] `src/styles/animations/` — `transitions.css` / `particles.css` / `glow.css`
- [ ] 11. [配置] 安装 GSAP（`npm install gsap`）用于复杂编排动画

#### Verification

1. `npm run tauri dev` → 设计系统 demo 页面所有组件正确渲染
2. 日/夜主题切换平滑，粒子背景跟随变化
3. `vue-tsc --noEmit` 零错误

---

## PR: phase-d-2-home-and-diary

- **Branch**: `feature/home-and-diary`
- **Depends on**: phase-d-1（design-system）
- **合并后 main**: 首页场景 + 日记写作场景可用

### Implementation Plan

#### Overview

实现核心用户流：首页 → 写日记 → AI 分析触发。

#### Tasks

- [ ] 1. [核心] `src/pages/HomeScene.vue` — "桌面"隐喻首页：日历贴纸视图、脉冲光晕"写日记"按钮、连续天数卡片、快速统计
- [ ] 2. [核心] `src/pages/DiaryScene.vue` — 全屏沉浸式书写区：羊皮纸/信纸风格、日期显示、情绪选择器、字数统计、可选的天气显示
- [ ] 3. [核心] `src/features/diary/DiaryEditor.vue` — 日记编辑器组件：watch content debounce 1s（隐式反馈信号）、标签选择
- [ ] 4. [核心] `src/features/diary/DiaryList.vue` — 日记列表组件：分页、`refresh()` expose
- [ ] 5. [核心] `src/stores/diary.ts` — Pinia store：当前日记状态、CRUD 操作
- [ ] 6. [核心] `src/shared/api/diary.ts` — API 模块：list/create/get/update/delete
- [ ] 7. [路由] 注册 `/` → HomeScene, `/write` → DiaryScene, `/write/:id` → DiaryScene

#### Verification

1. 首页正确显示日历贴纸（有日记的日期高亮）
2. 点击"写日记"进入写作场景，可以创建/编辑/删除日记
3. 日记保存后列表刷新

---

## PR: phase-d-3-analysis-and-review

- **Branch**: `feature/analysis-and-review`
- **Depends on**: phase-d-2（home-and-diary）
- **合并后 main**: AI 分析场景 + 历史回顾场景可用

### Implementation Plan

#### Overview

AI 分析结果展示 + 反馈互动 + 历史回顾（日历/时间线）。

#### Tasks

- [ ] 1. [核心] `src/pages/AnalysisScene.vue` — AI 回应以"来信"样式淡入；打字指示器；点赞/踩按钮（满足感动画）
- [ ] 2. [核心] `src/features/analysis/AIAnalysisPanel.vue` — AI 分析面板组件：展示 response、token 消耗、执行 tier
- [ ] 3. [核心] `src/features/analysis/FeedbackButtons.vue` — 赞/踩按钮：`+1`/`-1` 状态机；点击动画
- [ ] 4. [核心] `src/shared/api/analysis.ts` — API 模块：trigger/get
- [ ] 5. [核心] `src/shared/api/feedback.ts` — API 模块：submit
- [ ] 6. [核心] `src/pages/ReviewScene.vue` — 日历/时间线视图："书架"隐喻（每月一本书）；点击日期展开条目详情 + AI 分析
- [ ] 7. [核心] `src/features/review/CalendarView.vue` — 日历组件，有日记的日期用贴纸标记
- [ ] 8. [核心] `src/features/review/TimelineView.vue` — 时间线组件，日记条目按日期排列
- [ ] 9. [核心] `src/stores/analysis.ts` — Pinia store：当前分析状态
- [ ] 10. [路由] 注册 `/analysis/:diaryId` → AnalysisScene, `/review` → ReviewScene, `/review/:diaryId` → ReviewScene + 详情

#### Verification

1. 写日记后点击"AI 分析"→ analysis scene 正确展示结果
2. 点赞/踩正确发送反馈
3. 回顾页面日历/时间线正确展示历史日记

---

## PR: phase-d-4-settings-and-onboarding

- **Branch**: `feature/settings-and-onboarding`
- **Depends on**: phase-d-3（analysis-and-review）
- **合并后 main**: 设置场景 + 首次使用引导可用

### Implementation Plan

#### Overview

设置场景（LLM 配置、主题、备份）、首次使用叙事式引导。

#### Tasks

- [ ] 1. [核心] `src/pages/SettingsScene.vue` — 设置面板：分区平滑展开（通用/LLM/备份/关于）
- [ ] 2. [核心] `src/features/settings/LLMConfig.vue` — LLM 配置表单：添加/编辑/删除 provider，设为默认
- [ ] 3. [核心] `src/features/settings/BackupManager.vue` — 备份管理：手动备份、自动备份开关、备份列表、恢复
- [ ] 4. [核心] `src/features/settings/ThemeToggle.vue` — 主题切换：日/夜/跟随系统
- [ ] 5. [核心] `src/pages/OnboardingScene.vue` — 首次使用叙事式引导（非表单！）：AI 引擎下载进度、设置昵称/偏好、介绍核心功能
- [ ] 6. [核心] `src/stores/settings.ts` — Pinia store：应用设置持久化（通过 Tauri 文件 API 或 localStorage）
- [ ] 7. [核心] `src/shared/api/settings.ts` — API 模块：models CRUD, backup, stats
- [ ] 8. [核心] `src/composables/useTheme.ts` — 主题 composable：日/夜/auto，平滑过渡
- [ ] 9. [核心] `src/composables/useSound.ts` — 音效 composable：Web Audio API，默认关闭
- [ ] 10. [路由] 注册 `/settings` → SettingsScene, `/settings/llm`, `/settings/backup`, `/onboarding` → OnboardingScene
- [ ] 11. [配置] `src/router/index.ts` — Vue Router 路由配置 + 首次使用重定向（无日记 → onboarding）

#### Verification

1. 设置页面各分区可展开，配置正确保存
2. 首次运行 → onboarding 引导流程
3. 日/夜主题切换流畅

---

## PR: phase-e-1-delivery

- **Branch**: `chore/delivery`
- **Depends on**: Phase D 全部完成
- **合并后 main**: 双击 .exe 可运行；README 完整

### Implementation Plan

#### Overview

PyInstaller 打包 Python → Tauri build 生成 Windows 安装器 → E2E 验证 → 文档。

#### Tasks

- [ ] 1. [核心] `server/build.spec` — 最终 PyInstaller spec（含 torch/chromadb/onnxruntime/sentence-transformers/jieba 所有 hidden imports + 二进制依赖）
- [ ] 2. [核心] Tauri build 配置 — `tauri.conf.json`：bundle 配置，嵌入 Python .exe 为 resource；Windows 安装器（NSIS/Inno Setup）
- [ ] 3. [核心] 模型下载器 — 首次启动下载 embedding/reranker 模型（从 HuggingFace 镜像），进度条 UI，断点续传
- [ ] 4. [核心] 自动备份 — Rust 侧应用退出前 copy `night_diary.db` → `backups/YYYY-MM-DDTHHmmss-auto.db`
- [ ] 5. [测试] E2E 测试 — Playwright（或 Tauri driver）：日记 CRUD → AI 分析 → 反馈完整流程
- [ ] 6. [测试] 性能验证 — embedding 模型 warmup 时间、LLM 调用延迟、SQLite 查询性能
- [ ] 7. [文档] `README.md` 最终版
- [ ] 8. [文档] `docs/user-guide.md` — 用户指南（安装、LLM 配置、备份恢复）
- [ ] 9. [文档] `docs/dev-guide.md` — 开发者指南（环境搭建、目录结构、构建流程）

#### Verification

1. `make build` 生成可双击运行的 .exe（或安装器）
2. 安装后首次启动 → onboarding → 写日记 → AI 分析 → 反馈 → 回顾 完整通过
3. 数据文件在 `%APPDATA%/night-diary/` 下正确存储
4. 所有文档可读、步骤可复现

---

## 附录 A：AI 分析路由决策

（沿用 V1 的分级设计，迁移时保留）

| 级别 | 触发条件 | 激活 Agent | 预估 Token |
|------|----------|-----------|-----------|
| **Light** | 简短日记（< 100 字）+ 纯记录意图 | Empathy only | 400-600 |
| **Medium** | 含历史回溯 / 情绪表达 | Retrieval + Empathy | 1000-1500 |
| **Heavy** | 深度反思长文 / 周月总结请求 | All three Workers | 1500-2500 |
| **Crisis** | 危机检测（极端负面情绪） | 短路 → 安全模板 | ~200 |

路由优先级：`Multi-Agent（langgraph 可用）> ReAct Agent（含时间回溯关键词）> Chain（直接 LLM 生成）> Fallback（硬编码安全回应）`

## 附录 B：V1 迁移参考

（迁移时保持 V1 逻辑正确性的对照表）

| V1 源文件 | V2 目标 | 迁移方式 |
|-----------|---------|---------|
| `agents/intent_classifier.py` | `domain/agents/intent_classifier.py` | **直接迁移**（设计最干净的模块） |
| `agents/graph.py` | `domain/agents/graph.py` | 迁移 + DI 改造 |
| `agents/supervisor.py` | `domain/agents/supervisor.py` | 迁移 + 集成 SkillRegistry |
| `agents/empathy_agent.py` | `domain/agents/empathy_agent.py` | 迁移 + DI 改造 + 共享工具 |
| `agents/retrieval_agent.py` | `domain/agents/retrieval_agent.py` | 迁移 + DI 改造 + 共享工具 |
| `agents/insight_agent.py` | `domain/agents/insight_agent.py` | 迁移 + DI 改造 |
| `services/ai_service.py`（987 行） | `services/ai/` 目录（7 模块） | **拆分为 7 个独立模块** |
| `services/vector_service.py`（771 行） | `domain/rag/` 目录（5 模块，分 B-2 基础 + B-3 检索两阶段交付） | **拆分为 5 个独立模块** |
| `memory/episodic.py` | `domain/memory/episodic.py` | 迁移 + Redis → 进程内 deque + **SQLite 默认持久化** |
| `memory/long_term.py` | `domain/memory/long_term.py` | 迁移 + MySQL JSON → SQLite JSON |
| `memory/working.py` | `domain/memory/working.py` | 迁移 + **实际集成** |
| `skills/` 目录（12 文件） | `domain/skills/` 目录 | 迁移（MVP: 激活 2 个，其余 stub）+ **B-9 集成到 Supervisor** |
| `feedback/thompson_sampling.py` | `domain/feedback/thompson_sampling.py` | 基本不变，消除重复 |
| `feedback/prompt_tuner.py` | `domain/feedback/prompt_tuner.py` | 迁移 + 调用 ThompsonSampling |
| `knowledge/domain_store.py` | `domain/knowledge/store.py` | 迁移 + 唯一查询入口 |
| `knowledge/extractor.py` | `domain/knowledge/extractor.py` | 迁移 + 修复 bug |
| `routers/diary.py` | `api/v1/diary.py` | **重写**（去 auth/user_id） |
| `routers/analysis.py` | `api/v1/analysis.py` | **重写**（去 auth） |
| `routers/auth.py` | — | **删除** |
| `routers/admin.py` | — | **删除** |
| `routers/public_column.py` | — | **删除** |
| 前端 `DiaryPage.vue` 等 | `src/pages/` | 参考业务逻辑，UI **完全重写** |

---

> **施工顺序**：Phase A → E，每 PR 合并后 `main` 必须可运行。当前进度见 `.cursor/rules/current_phase.mdc`。
