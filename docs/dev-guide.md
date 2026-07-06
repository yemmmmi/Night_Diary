# 夜记开发者指南

## 环境要求

| 工具 | 版本 |
|------|------|
| Python | 3.11.x |
| Node.js | 20+ |
| Docker | 24+（Web 端部署） |

## 仓库结构

```
night-diary-v2/
├── src/                # Vue 3 前端
├── server/             # Python FastAPI 后端
│   ├── app/            # 应用代码
│   └── tests/          # pytest（unit / e2e / smoke / eval）
├── Dockerfile          # 前端多阶段构建（node:20 → nginx:alpine）
├── docker-compose.yml  # 生产编排（MySQL + Redis + Backend + Worker + Frontend）
└── docs/               # 文档
```

分层约定：`api → services → domain → shared + infrastructure`

## 本地开发

### 方式一：Docker Compose（推荐）

```bash
cp .env.example .env   # 编辑 JWT_SECRET_KEY、MODEL_KEY_SECRET、LLM_API_KEY

# 生产模式（MySQL + Redis + 全服务）
docker compose up -d

# 开发模式（SQLite + 内存降级，跳过 MySQL/Redis）
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

访问 `http://localhost`（前端）或 `http://localhost:8000/docs`（API 文档）。

### 方式二：本地直接运行（无 Docker）

```bash
# 后端依赖
cd server
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# 前端依赖（仓库根目录，另一终端）
cd ..
npm install
npm run dev            # http://localhost:5173
```

### 环境变量（`server/.env`）

```env
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
MODEL_KEY_SECRET=至少16字节的Fernet密钥
HF_ENDPOINT=https://hf-mirror.com
```

## 测试

```bash
make test              # pytest + vitest
make e2e               # API 端到端（日记→分析→反馈）
make smoke             # 性能冒烟（health / SQLite 列表延迟）
make eval-rag          # RAG 离线评估（需 [eval] 依赖）
```

## 生产构建

```bash
docker compose -f docker-compose.yml build
docker compose -f docker-compose.yml up -d
```

镜像产物：

| 镜像 | 说明 |
|------|------|
| `night-diary-frontend` | Vue 3 静态资源 + nginx:alpine |
| `night-diary-backend` | Python 3.12-slim + uvicorn 4 workers |

## 关键模块

| 模块 | 职责 |
|------|------|
| `server/app/main.py` | FastAPI 入口、`/health` `/ready` `/shutdown` |
| `server/app/services/model_downloader.py` | 首次模型下载（HF 镜像） |
| `server/app/services/container.py` | DI 容器、AI 栈懒加载 |
| `server/app/domain/agents/graph.py` | Multi-Agent 编排入口 |

## 贡献流程

1. 从 `main` 拉取最新：`git checkout main && git pull`
2. 创建分支：`feature/` `fix/` `chore/` 等
3. 提交前：`make lint && make test`
4. 通过 PR 合并，勿直接 push `main`
