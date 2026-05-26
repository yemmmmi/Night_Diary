# Night Diary V2

夜间日记 V2 —— 在新仓库中从零重建的版本。

- **完整施工蓝图**：[`task.md`](./task.md)（18 个 PR 章节）
- **架构与规范**：[`.cursor/rules/`](./.cursor/rules/)
- **当前进度**：[`.cursor/rules/current_phase.mdc`](./.cursor/rules/current_phase.mdc)

## 技术栈

| 层 | 技术 |
|----|------|
| 后端（`server/`） | Python 3.11 · FastAPI · SQLAlchemy 2 · Alembic · pydantic-settings · Redis |
| 前端（`web/`） | Vue 3 · TypeScript · Vite · Tailwind CSS · Vitest |
| 基础设施 | MySQL 8 · Redis 7（本地通过 Docker Compose） |
| AI | LangChain / LangGraph · Chroma · BM25 · jieba（Phase 2 起接入） |

## 目录结构

```
night-diary-v2/
├── server/                  # 后端
│   ├── app/
│   │   ├── api/v1/          # 路由层（薄层，Phase 3 实现）
│   │   ├── services/        # 服务层（业务编排，Phase 3）
│   │   ├── domain/          # 领域层（agents / memory / skills / feedback / knowledge / rag，Phase 2）
│   │   ├── shared/          # 错误类型、LLM 工厂等
│   │   ├── infrastructure/  # DB / Redis / 安全（Phase 1）
│   │   ├── config.py        # pydantic-settings 配置
│   │   └── main.py          # FastAPI 入口
│   ├── tests/
│   ├── .env.example
│   └── pyproject.toml
├── web/                     # 前端
│   ├── src/
│   │   ├── pages/
│   │   ├── features/        # 按业务领域组织（Phase 4）
│   │   ├── shared/          # 类型/工具/composables
│   │   └── router/
│   ├── package.json
│   └── vite.config.ts
├── alembic/                 # 数据库迁移
├── .github/workflows/ci.yml # CI（pytest / vitest / mypy / vue-tsc / ruff / eslint）
├── docker-compose.yml       # 本地 MySQL + Redis
└── Makefile                 # 常用任务入口
```

## 快速开始（本地）

> 要求：Python 3.11+、Node.js 20+、Docker（含 Compose 插件）、GNU Make。

### 1. 配置环境变量

```bash
cp server/.env.example server/.env
cp web/.env.example web/.env
```

⚠️ 编辑 `server/.env`，把 `JWT_SECRET_KEY` 与 `MODEL_KEY_SECRET` 替换为强随机值。
缺失或长度不足 16 字符时，FastAPI 启动会失败（这是设计上的安全 fail-fast）。

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 2. 启动基础设施

```bash
make up           # docker compose up -d  (mysql + redis)
```

### 3. 安装依赖

```bash
# 后端
cd server
python -m venv .venv
.venv\Scripts\activate     # PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
cd ..

# 前端
cd web
npm install
cd ..
```

### 4. 数据库迁移

```bash
make migrate      # Phase 0 为空 schema，Phase 1 起会创建业务表
```

### 5. 启动开发服务

打开两个终端：

```bash
make dev-api      # http://localhost:8000   →  /health 返回 {"status":"ok"}
make dev-web      # http://localhost:5173   →  Vue 占位首页
```

## 常用 Make 目标

| 目标 | 作用 |
|------|------|
| `make up` / `make down` | 启停 Docker 基础设施 |
| `make logs` | 跟踪 Docker 日志 |
| `make migrate` | Alembic 迁移到 head |
| `make dev-api` / `make dev-web` | 启动开发服务 |
| `make test` | 跑 pytest + vitest |
| `make lint` | ruff + mypy + eslint + vue-tsc |
| `make format` | ruff format |

## 开发约定

详见 [`.cursor/rules/`](./.cursor/rules/)：

- [`architecture.mdc`](./.cursor/rules/architecture.mdc) — V2 分层与目录约定
- [`coding-standards.mdc`](./.cursor/rules/coding-standards.mdc) — Python / TypeScript 规范
- [`collaboration.mdc`](./.cursor/rules/collaboration.mdc) — Git / 分支 / PR 规范
- [`execution-plan.mdc`](./.cursor/rules/execution-plan.mdc) — 分阶段执行计划与迁移策略
- [`task.md`](./task.md) — 完整 18 个 PR 的施工蓝图

**核心原则**：

- 禁止直接 push 到 `main`；所有改动通过 PR 合并
- 后端分层方向单向：`api → services → domain → shared + infrastructure`
- 服务层不抛 `HTTPException`，统一抛 `AppError` 由路由层转换
- Agent / Skill 通过 DI 接收 LLM 和 DB，不在内部 `SessionLocal()` 或 `ChatOpenAI()`
- 无硬编码密钥，所有 secret 走环境变量

## V1 参考

V1 项目位于 `D:\work\night_diary`（只读参考），V2 **绝不** import V1 代码。迁移对照表见 `task.md` 附录 B。
