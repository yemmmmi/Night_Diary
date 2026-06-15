# 夜记开发者指南

## 环境要求

| 工具 | 版本 |
|------|------|
| Python | 3.11.x |
| Node.js | 20+ |
| Rust | stable（Tauri 构建） |
| Windows | 10 1809+（WebView2） |

## 仓库结构

```
night-diary-v2/
├── src-tauri/          # Rust 桌面壳（进程管理、备份、打包）
├── src/                # Vue 3 前端
├── server/             # Python FastAPI sidecar
│   ├── app/            # 应用代码
│   ├── build.spec      # PyInstaller 配置
│   └── tests/          # pytest（unit / e2e / smoke / eval）
├── scripts/            # 构建辅助脚本
└── docs/               # 文档
```

分层约定：`api → services → domain → shared + infrastructure`

## 本地开发

```bash
# 后端依赖
cd server
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"

# 前端依赖（仓库根目录）
cd ..
npm install

# 单终端桌面开发（推荐）
make dev-web

# 双终端：后端热重载 + Tauri attach
make dev-api          # 终端 1
make dev-web-fast     # 终端 2
```

浏览器纯前端调试：`npm run dev`（需另开 `make dev-api`）。

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

## 构建发布（Phase E-1）

完整桌面安装包：

```bash
# 1. 安装 AI 打包依赖（含 torch / sentence-transformers）
cd server && pip install -e ".[dev,eval]"

# 2. 一键构建（PyInstaller → 复制 sidecar → Tauri bundle）
cd ..
make build
```

分步：

```bash
make build-sidecar     # 仅 PyInstaller → dist/nightdiary-backend.exe
npm run prepare-sidecar  # 复制到 src-tauri/binaries/
npm run build          # 前端
npm run tauri build    # 桌面安装包
```

产物：

| 路径 | 说明 |
|------|------|
| `dist/nightdiary-backend.exe` | Python sidecar |
| `src-tauri/target/release/bundle/nsis/*.exe` | Windows 安装器 |

Tauri `externalBin` 将 sidecar 嵌入安装目录，与主程序同目录启动（见 `src-tauri/src/process.rs`）。

### PyInstaller 排错

- 缺模块：在 `server/build.spec` 的 `HIDDEN_IMPORTS` 添加后重建
- onnxruntime DLL：确保构建 venv 已安装 `onnxruntime` 和 `chromadb`
- 体积过大：含 torch 时 1–2 GB 属预期

## 关键模块

| 模块 | 职责 |
|------|------|
| `src-tauri/src/process.rs` | 启动 / 健康检查 / 关闭 Python sidecar |
| `src-tauri/src/backup.rs` | SQLite 备份恢复 + 退出自动备份 |
| `server/app/main.py` | FastAPI 入口、`/health` `/ready` `/shutdown` |
| `server/app/services/model_downloader.py` | 首次模型下载（HF 镜像） |
| `server/app/services/container.py` | DI 容器、AI 栈懒加载 |
| `server/app/domain/agents/graph.py` | Multi-Agent 编排入口 |

## 贡献流程

1. 从 `main` 拉取最新：`git checkout main && git pull`
2. 创建分支：`feature/` `fix/` `chore/` 等
3. 提交前：`make lint && make test`
4. 通过 PR 合并，勿直接 push `main`

详见 [`.cursor/rules/collaboration.mdc`](../.cursor/rules/collaboration.mdc)。
