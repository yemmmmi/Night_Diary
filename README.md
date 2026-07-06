# Night Diary V2

夜记 V2 —— AI 心理陪伴日记系统（Web 端）。

- **Web 端**：Docker Compose + MySQL + Redis + Neo4j，多用户 + JWT 认证

所有基础设施组件（Redis / Neo4j / MySQL / RQ / LangGraph）均实现优雅降级，不可用时自动回退。

## 技术栈

| 层 | Web 端 |
|----|--------|
| 前端 | Vue 3 · TypeScript · Vite · Tailwind CSS · Vitest（nginx:alpine 静态托管） |
| 后端 | Python 3.12 · FastAPI · uvicorn（Docker, 4 workers） |
| 数据库 | MySQL 8.0 (连接池 + utf8mb4) |
| 缓存 | Redis 7 (SessionContext + JWT 黑名单 + 模型配置) |
| 向量库 | ChromaDB |
| 实体图 | Neo4j 5 (实体关系图) |
| 任务队列 | RQ (Redis Queue) + Worker |
| 认证 | JWT (jti 黑名单, 7 天过期) |
| 反向代理 | Nginx (静态托管 + /api/ 代理 + WebSocket + gzip) |
| AI 编排 | asyncio MultiAgentGraph + ConversationLoop + LangGraph StateGraph (场景二, 可选) |
| AI 模型 | DeepSeek / OpenAI 兼容 API · bge-small-zh-v1.5 · bge-reranker-base |

## 两大 AI 业务场景

| 场景 | 描述 | 入口 |
|------|------|------|
| 写日记 → 回信 | 用户写日记（或记一笔卡片），系统生成回信 + 情绪分析 | `POST /api/v1/analysis/trigger` |
| 会话 → 多轮对话 | 用户与 AI 多轮对话，支持工具调用、记忆检索、实体查询 | `POST /api/v1/conversation/{id}/messages` |

两场景通过共享子组件互通：`ContentNormalizer`（三来源归一化）、`UnifiedMemoryAtom`（统一记忆原子）、`MemoryGateway`（四维检查 + 长期画像晋升）、`HybridEntityExtractor`（regex + LLM 双层实体提取）。

## 目录结构

```
night-diary-v2/
├── src/                        # Vue 3 前端
│   ├── pages/                  # 场景级页面（Diary / Chat / Analysis / Memory ...）
│   ├── features/               # 按业务领域组织（diary / chat / card / memory ...）
│   ├── shared/                 # API / 组件 / composables / stores / utils
│   ├── stores/                 # Pinia（auth / diary / chat / analysis ...）
│   └── styles/                 # 主题 + 动画
├── server/                     # Python AI 引擎（FastAPI）
│   ├── app/
│   │   ├── main.py             # 入口（绑 0.0.0.0）
│   │   ├── config.py           # pydantic-settings 配置
│   │   ├── api/v1/             # 路由层（auth / diary / conversation / analysis ...）
│   │   ├── services/           # 业务编排
│   │   │   ├── ai/             # Agent 编排（conversation_loop / graph_nodes / input_preprocessor ...）
│   │   │   ├── container.py    # DI 容器
│   │   │   ├── analysis_service.py      # 场景一入口
│   │   │   ├── conversation_ai_service.py # 场景二入口
│   │   │   ├── memory_gateway.py        # 统一记忆写入
│   │   │   └── normalizer.py            # ContentNormalizer 三来源归一化
│   │   ├── domain/             # 领域模型
│   │   │   ├── agents/         # IntentClassifier / ChatIntentClassifier / SlotExtractor / EntityExtractor ...
│   │   │   ├── memory/         # EpisodicMemory / LongTermMemory / UnifiedMemoryAtom
│   │   │   ├── skills/         # SkillRegistry（crisis / sentiment / memory_recall / entity_tracker）
│   │   │   ├── feedback/       # ThompsonSampling / PromptTuner / ImplicitStyle
│   │   │   ├── rag/            # ChromaDB 检索 + BM25 + reranker
│   │   │   ├── knowledge/      # 实体知识存储
│   │   │   └── orchestrator.py # OrchestratorProtocol 统一编排协议
│   │   ├── infrastructure/     # 基础设施
│   │   │   ├── database.py     # 双引擎（SQLite / MySQL）
│   │   │   ├── redis_client.py # Redis（降级到内存）
│   │   │   ├── entity_graph.py # Neo4j（降级到 SQLite）
│   │   │   ├── session_cache.py # SessionContext L1+L2
│   │   │   ├── jwt_blacklist.py # JWT 黑名单
│   │   │   ├── task_queue.py   # RQ（降级到 daemon thread）
│   │   │   ├── auth.py         # JWT 认证
│   │   │   ├── mcp_server.py   # MCP 工具暴露
│   │   │   └── ...
│   │   └── workers/            # RQ Worker
│   ├── alembic/                # 数据库迁移
│   ├── tests/                  # unit / e2e / eval / smoke
│   ├── Dockerfile              # Python 3.12-slim + uvicorn 4 workers
│   └── pyproject.toml
├── Dockerfile                  # 前端多阶段构建（node:20 → nginx:alpine）
├── docker-compose.yml          # 生产编排（MySQL + Redis + Backend + Worker + Frontend）
├── docker-compose.dev.yml      # 开发 override（SQLite + 内存降级）
├── nginx.conf                  # Nginx 配置（静态 + /api/ 代理 + WebSocket + gzip）
├── Makefile
└── docs/                       # 文档
```

## 快速开始

> 要求：Docker + Docker Compose。

```bash
# 复制环境变量
cp .env.example .env
# 编辑 .env：设置 JWT_SECRET_KEY、MODEL_KEY_SECRET、LLM_API_KEY

# 生产模式（MySQL + Redis + 全服务）
docker compose up -d

# 开发模式（SQLite + 内存降级，跳过 MySQL/Redis）
docker compose -f docker-compose.yml -f docker-compose.dev.yml up

# 可选：启动 Neo4j 实体图
docker compose --profile graph up -d neo4j

# 可选：启动 Worker（开发模式默认跳过）
docker compose --profile full up -d worker
```

访问 `http://localhost`（前端）或 `http://localhost:8000/docs`（API 文档）。

### 本地开发（无 Docker）

```bash
# 后端
cd server
python -m venv .venv && .venv\Scripts\activate  # Windows
pip install -e ".[dev]"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# 前端（另一终端）
npm install
npm run dev   # http://localhost:5173
```

### LLM 配置

- 开发时在 `server/.env` 或 `.env` 设置 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL` 作为默认回退
- **设置页保存的模型优先级更高**；推荐在应用内「设置 → AI 模型」配置 DeepSeek
- DeepSeek Base URL 填 `https://api.deepseek.com/v1`；模型名用 `deepseek-chat` 或 `deepseek-reasoner`

## 常用 Make 目标

| 目标 | 作用 |
|------|------|
| `make dev-api` | 启动 Python 后端（热重载，127.0.0.1:8000） |
| `make dev-web` | 启动 Vue 3 前端开发服务器（5173） |
| `make test` | pytest + vitest |
| `make lint` | ruff + mypy + eslint + vue-tsc |
| `make eval` | 离线 eval 测试（真实 LLM，需 `[eval]` extra） |
| `make e2e` | API 端到端流程测试 |
| `make smoke` | 性能冒烟检查 |

## 生产构建

```bash
docker compose -f docker-compose.yml build
docker compose -f docker-compose.yml up -d
```

详见 [`docs/dev-guide.md`](./docs/dev-guide.md) 与 [`docs/user-guide.md`](./docs/user-guide.md)。

## 开发约定

- 禁止直接 push 到 `main`；所有改动通过 PR 合并
- 后端分层方向单向：`api → services → domain → shared + infrastructure`
- 服务层不抛 `HTTPException`，统一抛 `AppError` 由路由层转换
- Agent / Skill 通过 DI 接收 LLM 和 DB，不在内部自行创建
- 无硬编码密钥，所有 secret 走环境变量
- 所有基础设施组件必须实现优雅降级
- Memory 层操作必须包含 `user_id` 参数（多租户隔离）

详见 [`CLAUDE.md`](./CLAUDE.md)。

## 数据存储

Docker 命名卷：

| 卷 | 用途 |
|----|------|
| `mysql_data` | MySQL 数据 |
| `redis_data` | Redis 持久化 |
| `neo4j_data` | Neo4j 实体图 |
| `backend_data` | 后端数据目录（备份 / 日志 / ChromaDB） |

## V1 参考

V1 项目位于 `D:\work\night_diary`（只读参考），V2 **绝不** import V1 代码。
