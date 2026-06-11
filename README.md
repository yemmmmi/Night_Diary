# Night Diary V2

夜记 V2 —— AI 心理陪伴日记系统，**本地桌面应用**。

双击 `.exe` 即可打开，所有数据存储在本地。无需登录、无需 Docker、无需联网（LLM API 调用除外）。

> **架构转型说明**: V2 已从 Web 多用户架构转为本地桌面端。详细方案见 [`docs/本地化桌面端重构方案.md`](./docs/本地化桌面端重构方案.md)。

- **架构与规范**：[`.cursor/rules/`](./.cursor/rules/)
- **当前进度**：[`.cursor/rules/current_phase.mdc`](./.cursor/rules/current_phase.mdc)

## 技术栈

| 层 | 技术 |
|----|------|
| 桌面壳 | Tauri v2 (Rust) + 系统 WebView2 |
| 前端 | Vue 3 · TypeScript · Vite · Tailwind CSS · Vitest |
| AI 引擎 | Python 3.11 · FastAPI · LangChain / LangGraph · ChromaDB |
| 数据存储 | SQLite（结构化数据）· ChromaDB（向量存储） |
| AI 模型 | text2vec-base-chinese · bge-reranker-base · DeepSeek / OpenAI 兼容 API |

## 目录结构

```
night-diary-v2/
├── src-tauri/              # Tauri (Rust) 桌面壳
├── src/                    # Vue 3 前端（原 web/，Tauri 标准布局，WebView 内运行）
│   ├── pages/              # 场景级页面
│   ├── features/           # 按业务领域组织
│   ├── shared/             # API / 组件 / composables / stores / types
│   └── styles/             # 主题 + 动画
├── server/                 # Python AI 引擎（FastAPI sidecar）
│   └── app/
│       ├── main.py         # 入口（127.0.0.1，无 CORS，无 auth）
│       ├── config.py       # pydantic-settings + CLI 参数
│       ├── domain/         # agents / memory / skills / feedback / knowledge / rag
│       ├── services/       # 业务编排
│       ├── api/v1/         # 路由层
│       ├── shared/         # 错误类型、LLM 工厂
│       └── infrastructure/ # DB / 模型
├── docs/                   # 文档
├── .github/workflows/      # CI
└── Makefile
```

## 快速开始（开发）

> 要求：Python 3.11+、Node.js 20+、Rust 工具链。

```bash
# 1. 后端
cd server
python -m venv .venv && .venv\Scripts\activate  # Windows
pip install -e ".[dev]"

# 2. 前端
cd ..
npm install

# 3. 启动桌面应用（推荐单终端，后端随 Tauri 一起启停）
npm run tauri dev   # Ctrl+C 会同时关闭 Tauri 与 :8000 后端

# 双终端（后端独立热重载，Tauri 只 attach，退出时不关后端）
# 终端 1: cd server && python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
# 终端 2 (PowerShell): $env:NIGHTDIARY_DEV_BACKEND_ATTACH=1; npm run tauri dev

# 仅调试前端（浏览器，非 Tauri）
npm run dev       # Vite → http://localhost:5173（需配合 dev-api）
```

### LLM 配置（`.env` 与设置页）

- 开发时在 `server/.env` 可设置 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL` 作为默认回退。
- **设置页保存的模型优先级更高**；推荐在应用内「设置 → AI 模型」配置 DeepSeek。
- DeepSeek Base URL 填 `https://api.deepseek.com/v1`；模型名用 `deepseek-chat` 或 `deepseek-reasoner`（不要用不存在的模型 id）。
- 修改 Python 后端代码后，若 API 报 405/404，请重启 `make dev-api` 或确认 uvicorn 已 `--reload`。

## 常用 Make 目标

| 目标 | 作用 |
|------|------|
| `make dev-api` | 启动 Python 后端（热重载，仅 127.0.0.1） |
| `make dev-web` | 启动 Tauri（自动启停 :8000 后端，Ctrl+C 一并退出） |
| `make dev-web-fast` | Tauri + 已有 `dev-api`（attach 模式，不关闭后端） |
| `make test` | 跑 pytest + vitest |
| `make lint` | ruff + mypy + eslint + vue-tsc |
| `make format` | ruff format |

## 开发约定

详见 [`.cursor/rules/`](./.cursor/rules/)：

- [`architecture.mdc`](./.cursor/rules/architecture.mdc) — V2 分层与目录约定（已更新为桌面端架构）
- [`coding-standards.mdc`](./.cursor/rules/coding-standards.mdc) — Python / TypeScript 规范
- [`collaboration.mdc`](./.cursor/rules/collaboration.mdc) — Git / 分支 / PR 规范
- [`execution-plan.mdc`](./.cursor/rules/execution-plan.mdc) — 新版分阶段执行计划

**核心原则**：

- 禁止直接 push 到 `main`；所有改动通过 PR 合并
- 后端分层方向单向：`api → services → domain → shared + infrastructure`
- 服务层不抛 `HTTPException`，统一抛 `AppError` 由路由层转换
- Agent / Skill 通过 DI 接收 LLM 和 DB，不在内部自行创建
- 无硬编码密钥，所有 secret 走环境变量或 CLI 参数

## 数据存储

所有数据存储在 `%APPDATA%/night-diary/`（Windows）：

```
night-diary/
├── night_diary.db      # SQLite 主数据库
├── chroma_data/        # ChromaDB 向量库
├── models/             # AI 模型文件
├── backups/            # 自动备份
└── logs/               # 运行日志
```

## V1 参考

V1 项目位于 `D:\work\night_diary`（只读参考），V2 **绝不** import V1 代码。
