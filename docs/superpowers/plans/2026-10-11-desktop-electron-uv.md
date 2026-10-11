# 夜记桌面端（Electron + uv 运行时）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让夜记以「双击即用」的原生窗口启动——Electron 宿主自动起本地 FastAPI 后端、把现有 Vue Web UI 装进窗口，Python 运行时用 uv + python-build-standalone 以可重定位目录交付（不用 PyInstaller），最终产出带签名的 Windows NSIS 安装包。

**Architecture:** 采用 DeepSeek Harness Desktop 的「宿主 + 本地进程 + 其 Web UI」模式。Electron 主进程分配随机 loopback 端口 → spawn 打包好的 Python 后端（`python -m app.main --port <p> --data-dir <d> --frontend-dir <f>`）→ 轮询 `/ready` → `BrowserWindow.loadURL(http://127.0.0.1:<p>/)`。**由后端自己托管构建后的前端**，因此页面与 API 同源，无 CORS、无端口注入到 axios 的复杂性；前端仅需一处改动：`resolveBackendBaseUrl()` 优先读取运行时注入的 `window.__NIGHT_DIARY__.backendUrl`。

**Tech Stack:** Electron 33 · electron-builder 25（NSIS）· TypeScript · Vitest（node 环境）· uv + python-build-standalone · FastAPI/uvicorn（既有）· Vue 3 + Vite（既有）

---

## 为什么这个方案不会重蹈归档方案覆辙

归档的 `docs/archive/本地化桌面端重构方案.md` 失败在**用 PyInstaller 把 torch + sentence-transformers + chromadb + onnxruntime 冻结成单个 exe**。本方案规避了这一点：

1. **核心运行时本就不含 torch**——`server/pyproject.toml` 把 `sentence-transformers`/`torch` 放在**可选 `eval` 组**，运行时依赖只有 fastapi/uvicorn/sqlalchemy/chromadb 等。
2. **embedding/rerank 走云端**——`config.py` 已有 `embedding_api_key`/`rerank_api_key`，设置后 `build_embedding_function` 优先用 OpenAI 兼容端点，**完全跳过本地模型下载与 torch**。
3. **运行时用 uv 目录式交付**——python-build-standalone 是官方可重定位发行版，`onnxruntime`/`chromadb` 的原生 DLL 以「安装」而非「冻结」方式落地，避开了 PyInstaller 的原生依赖地狱。
4. **后端已为桌面化预留**——`main.py` 已有 `--port`/`--data-dir` CLI 参数与 `multiprocessing.freeze_support()`；`config.py` 的 `data_dir` 默认就是 `%APPDATA%/night-diary`；`/health`、`/ready` 健康探针现成。

**体积预算（预估）**：Electron 壳 ~200MB + Python 运行时与依赖 ~250–400MB（无 torch）+ 前端 dist ~5MB ≈ **450–600MB**（对比归档方案 1.2–1.8GB）。若后续引入本地模型则另计。

**明确不做（YAGNI）**：不引入本地 sentence-transformers/torch（保持云端优先）；不做 macOS/Linux 打包（先 Windows x64）；不做自动更新（留到后续 PR）；不改动现有 Docker/Web 多用户路径（桌面是**新增启动方式**，非替换）。

---

## File Structure

**修改（既有代码）**
- `src/shared/composables/useBackend.ts` — `resolveBackendBaseUrl` 增加运行时注入分支
- `src/env.d.ts` — 声明 `window.__NIGHT_DIARY__` 类型
- `server/app/config.py` — 新增 `frontend_dir` 配置
- `server/app/main.py` — 新增 `--frontend-dir` 参数 + 静态托管挂载
- `.gitignore` — 忽略桌面构建产物

**新增（桌面包 `desktop/`，独立 npm 包，与 Web 前端解耦）**
- `desktop/package.json` — Electron 应用清单与脚本
- `desktop/tsconfig.json` — 编译 `src/*.ts` → `dist/*.js`
- `desktop/vitest.config.ts` — node 环境测试配置
- `desktop/src/paths.ts` — 纯函数：解析运行时/服务端/前端资源路径（可注入、可测）
- `desktop/src/port.ts` — 分配空闲 loopback 端口
- `desktop/src/backend.ts` — `BackendProcess`：spawn 后端、轮询 `/ready`、优雅停止
- `desktop/src/argv.ts` — 纯函数：从 `process.argv` 解析 `--backend-url`
- `desktop/src/preload.ts` — 通过 `contextBridge` 暴露 `window.__NIGHT_DIARY__`
- `desktop/src/main.ts` — Electron 主进程编排（薄胶水，由冒烟测试覆盖）
- `desktop/scripts/build-runtime.ps1` — uv 构建可重定位 Python 运行时
- `desktop/scripts/build-all.ps1` — 一键：前端构建 → 运行时 → electron-builder
- `desktop/electron-builder.yml` — NSIS 打包配置
- `desktop/tests/paths.spec.ts` / `port.spec.ts` / `argv.spec.ts` / `backend.spec.ts`

**新增（测试）**
- `src/__tests__/useBackend.spec.ts`
- `server/tests/unit/api/test_frontend_static_mount.py`

---

## Phase A — 契约层改动（前后端各一处，最小侵入）

### Task 1: 前端支持运行时注入后端地址

**Files:**
- Modify: `src/env.d.ts`
- Modify: `src/shared/composables/useBackend.ts:37-39`
- Test: `src/__tests__/useBackend.spec.ts`

- [ ] **Step 1: 写失败测试**

创建 `src/__tests__/useBackend.spec.ts`：

```ts
import { afterEach, describe, expect, it } from 'vitest'

import { resolveBackendBaseUrl } from '@/shared/composables/useBackend'

describe('resolveBackendBaseUrl', () => {
  afterEach(() => {
    delete (window as unknown as { __NIGHT_DIARY__?: unknown }).__NIGHT_DIARY__
  })

  it('prefers the runtime-injected backend url', async () => {
    ;(window as unknown as { __NIGHT_DIARY__?: { backendUrl?: string } }).__NIGHT_DIARY__ = {
      backendUrl: 'http://127.0.0.1:9123',
    }
    await expect(resolveBackendBaseUrl()).resolves.toBe('http://127.0.0.1:9123')
  })

  it('falls back to the dev default when nothing is injected', async () => {
    await expect(resolveBackendBaseUrl()).resolves.toBe('http://127.0.0.1:8000')
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `npx vitest run src/__tests__/useBackend.spec.ts`
Expected: 第 1 个用例 FAIL（当前实现忽略注入，返回 `http://127.0.0.1:8000`）

- [ ] **Step 3: 声明注入类型**

将 `src/env.d.ts` **整体替换**为下面的内容：

```ts
/// <reference types="vite/client" />

declare global {
  interface ImportMetaEnv {
    readonly VITE_API_BASE_URL?: string
  }

  interface ImportMeta {
    readonly env: ImportMetaEnv
  }

  interface Window {
    /** Electron preload 注入；桌面模式指向本地后端同源地址。 */
    __NIGHT_DIARY__?: { backendUrl?: string }
  }
}

export {}
```

> **关键**：`env.d.ts` 当前是「全局脚本」（无顶层 `import`/`export`），因此原有的 `ImportMetaEnv`/`ImportMeta` 自动全局生效。一旦为暴露 `Window` 而加入 `export {}`，文件会变成「模块」，顶层接口就不再全局生效——所以必须把原有的两个接口**一并搬进** `declare global` 块，否则 `import.meta.env.VITE_API_BASE_URL` 会失去类型。

- [ ] **Step 4: 修改 `resolveBackendBaseUrl`**

替换 `src/shared/composables/useBackend.ts` 第 37-39 行：

```ts
export async function resolveBackendBaseUrl(): Promise<string> {
  const injected =
    typeof window !== 'undefined' ? window.__NIGHT_DIARY__?.backendUrl : undefined
  if (typeof injected === 'string' && injected.length > 0) {
    return injected
  }
  return import.meta.env.VITE_API_BASE_URL ?? DEFAULT_DEV_BASE_URL
}
```

- [ ] **Step 5: 运行测试确认通过**

Run: `npx vitest run src/__tests__/useBackend.spec.ts`
Expected: 2 passed

- [ ] **Step 6: 类型检查**

Run: `npm run type-check`
Expected: 无错误

- [ ] **Step 7: 提交**

```bash
git add src/env.d.ts src/shared/composables/useBackend.ts src/__tests__/useBackend.spec.ts
git commit -m "feat(desktop): resolve backend url from runtime injection (A: contract)"
```

---

### Task 2: 后端静态托管构建后的前端

**Files:**
- Modify: `server/app/config.py`（在 `uploads_dir` property 后新增字段）
- Modify: `server/app/main.py`（`_parse_args`、`main()`、`create_app` 末尾）
- Test: `server/tests/unit/api/test_frontend_static_mount.py`

- [ ] **Step 1: 写失败测试**

创建 `server/tests/unit/api/test_frontend_static_mount.py`：

```python
"""Desktop mode: the backend serves the built frontend at / (same-origin SPA)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_serves_index_and_keeps_health(tmp_path: Path) -> None:
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text(
        "<!doctype html><title>night-diary</title>", encoding="utf-8"
    )
    settings = Settings(data_dir=str(tmp_path / "data"), frontend_dir=str(frontend))
    client = TestClient(create_app(settings))

    root = client.get("/")
    assert root.status_code == 200
    assert "night-diary" in root.text
    # 显式路由优先于根挂载
    assert client.get("/health").json() == {"status": "ok"}


def test_disabled_when_frontend_dir_empty(tmp_path: Path) -> None:
    settings = Settings(data_dir=str(tmp_path / "data"), frontend_dir="")
    client = TestClient(create_app(settings))
    assert client.get("/").status_code == 404
```

- [ ] **Step 2: 运行测试确认失败**

Run（在 `server/` 目录）: `.\.venv\Scripts\python.exe -m pytest tests/unit/api/test_frontend_static_mount.py -q`
Expected: 第 1 个用例 FAIL（`/` 返回 404，未挂载）

- [ ] **Step 3: 新增 `frontend_dir` 配置**

在 `server/app/config.py` 的 `uploads_dir` property 之后插入：

```python
    @property
    def uploads_dir(self) -> str:
        return str(Path(self.data_dir) / "uploads")

    # ---- Desktop mode: serve the built frontend as a same-origin SPA ----
    frontend_dir: str = Field(
        default="",
        description="Directory of the built frontend (index.html + assets) served "
        "as a static SPA at '/'. Empty disables static serving "
        "(dev via Vite / Docker via nginx).",
    )
```

- [ ] **Step 4: 新增 `--frontend-dir` 参数并透传**

在 `server/app/main.py` 的 `_parse_args` 中，`--data-dir` 之后加一行：

```python
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data-dir", type=str, default=None)
    parser.add_argument("--frontend-dir", type=str, default=None)
```

在 `main()` 中，`if args.data_dir:` 分支之后加：

```python
    if args.data_dir:
        os.environ["DATA_DIR"] = args.data_dir
    if args.frontend_dir:
        os.environ["FRONTEND_DIR"] = args.frontend_dir
```

- [ ] **Step 5: 在 `create_app` 末尾挂载静态目录**

在 `server/app/main.py` 的 `create_app` 中，`return app` **之前**插入：

```python
    # Desktop mode: serve the built SPA at '/' when a frontend dir is provided.
    # Explicit routes (/health, /ready, /api/v1/*, /v1/*) are registered above,
    # so they take precedence over this catch-all mount.
    if cfg.frontend_dir and Path(cfg.frontend_dir).is_dir():
        from fastapi.staticfiles import StaticFiles

        app.mount(
            "/",
            StaticFiles(directory=cfg.frontend_dir, html=True),
            name="frontend",
        )

    return app
```

> `Path` 已在 `main.py` 顶部导入，无需新增 import。

- [ ] **Step 6: 运行测试确认通过**

Run（在 `server/` 目录）: `.\.venv\Scripts\python.exe -m pytest tests/unit/api/test_frontend_static_mount.py -q`
Expected: 2 passed

- [ ] **Step 7: 后端 lint + 类型**

Run（在 `server/` 目录）:
```
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m mypy app
```
Expected: `All checks passed!` / `Success: no issues found`

- [ ] **Step 8: 提交**

```bash
git add server/app/config.py server/app/main.py server/tests/unit/api/test_frontend_static_mount.py
git commit -m "feat(server): serve built frontend as same-origin SPA (desktop mode)"
```

---

## Phase B — Electron 宿主

### Task 3: 初始化 `desktop/` 包与测试配置

**Files:**
- Create: `desktop/package.json`
- Create: `desktop/tsconfig.json`
- Create: `desktop/vitest.config.ts`

- [ ] **Step 1: 创建 `desktop/package.json`**

```json
{
  "name": "night-diary-desktop",
  "private": true,
  "version": "0.1.0",
  "description": "Night Diary desktop host (Electron shell + local Python backend).",
  "main": "dist/main.js",
  "scripts": {
    "build": "tsc -p tsconfig.json",
    "test": "vitest run",
    "dev": "npm run build && electron .",
    "dist": "npm run build && electron-builder --win nsis --config electron-builder.yml"
  },
  "devDependencies": {
    "@types/node": "^22.19.19",
    "electron": "^33.0.0",
    "electron-builder": "^25.0.0",
    "typescript": "~5.6.3",
    "vitest": "^3.0.5"
  }
}
```

- [ ] **Step 2: 创建 `desktop/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "CommonJS",
    "moduleResolution": "Node",
    "outDir": "dist",
    "rootDir": "src",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "sourceMap": true,
    "types": ["node"]
  },
  "include": ["src/**/*.ts"]
}
```

- [ ] **Step 3: 创建 `desktop/vitest.config.ts`**

```ts
import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    environment: 'node',
    include: ['tests/**/*.spec.ts'],
  },
})
```

- [ ] **Step 4: 安装依赖**

Run（在 `desktop/` 目录）: `npm install`
Expected: 安装成功，生成 `desktop/package-lock.json`

- [ ] **Step 5: 提交**

```bash
git add desktop/package.json desktop/package-lock.json desktop/tsconfig.json desktop/vitest.config.ts
git commit -m "chore(desktop): scaffold electron host package"
```

---

### Task 4: 空闲 loopback 端口分配

**Files:**
- Create: `desktop/src/port.ts`
- Test: `desktop/tests/port.spec.ts`

- [ ] **Step 1: 写失败测试**

创建 `desktop/tests/port.spec.ts`：

```ts
import { describe, expect, it } from 'vitest'

import { findFreePort } from '../src/port'

describe('findFreePort', () => {
  it('returns a usable ephemeral port', async () => {
    const port = await findFreePort()
    expect(Number.isInteger(port)).toBe(true)
    expect(port).toBeGreaterThan(1024)
    expect(port).toBeLessThanOrEqual(65535)
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run（在 `desktop/` 目录）: `npm test`
Expected: FAIL（`Cannot find module '../src/port'`）

- [ ] **Step 3: 实现 `findFreePort`**

创建 `desktop/src/port.ts`：

```ts
import net from 'node:net'

/** 让 OS 分配一个空闲端口并立即释放，返回该端口号。 */
export function findFreePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = net.createServer()
    server.unref()
    server.on('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const address = server.address()
      const port = typeof address === 'object' && address ? address.port : 0
      server.close(() => resolve(port))
    })
  })
}
```

- [ ] **Step 4: 运行测试确认通过**

Run（在 `desktop/` 目录）: `npm test`
Expected: 1 passed

- [ ] **Step 5: 提交**

```bash
git add desktop/src/port.ts desktop/tests/port.spec.ts
git commit -m "feat(desktop): free loopback port allocation"
```

---

### Task 5: 资源路径解析（纯函数）

**Files:**
- Create: `desktop/src/paths.ts`
- Test: `desktop/tests/paths.spec.ts`

- [ ] **Step 1: 写失败测试**

创建 `desktop/tests/paths.spec.ts`：

```ts
import path from 'node:path'

import { describe, expect, it } from 'vitest'

import { resolveBackendPaths } from '../src/paths'

describe('resolveBackendPaths', () => {
  it('resolves bundled resources in packaged mode', () => {
    const out = resolveBackendPaths({
      packaged: true,
      resourcesPath: 'C:/App/resources',
      repoRoot: 'C:/repo',
    })
    expect(out.pythonExe).toBe(path.join('C:/App/resources', 'runtime', 'python.exe'))
    expect(out.serverDir).toBe(path.join('C:/App/resources', 'server'))
    expect(out.frontendDir).toBe(path.join('C:/App/resources', 'frontend'))
  })

  it('uses the repo layout in dev mode and honours a python override', () => {
    const out = resolveBackendPaths({
      packaged: false,
      resourcesPath: 'ignored',
      repoRoot: 'C:/repo',
      pythonOverride: 'C:/repo/server/.venv/Scripts/python.exe',
    })
    expect(out.pythonExe).toBe('C:/repo/server/.venv/Scripts/python.exe')
    expect(out.serverDir).toBe(path.join('C:/repo', 'server'))
    expect(out.frontendDir).toBe(path.join('C:/repo', 'dist'))
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run（在 `desktop/` 目录）: `npm test`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 `resolveBackendPaths`**

创建 `desktop/src/paths.ts`：

```ts
import path from 'node:path'

export interface PathInputs {
  packaged: boolean
  resourcesPath: string
  repoRoot: string
  pythonOverride?: string
}

export interface BackendPaths {
  pythonExe: string
  serverDir: string
  frontendDir: string
}

/**
 * 打包态：运行时/服务端/前端都作为 extraResources 放在 resources/ 下。
 * 开发态：复用仓库布局与本地 venv（可用 NIGHT_DIARY_PYTHON 覆盖）。
 */
export function resolveBackendPaths(inputs: PathInputs): BackendPaths {
  if (inputs.packaged) {
    return {
      pythonExe: path.join(inputs.resourcesPath, 'runtime', 'python.exe'),
      serverDir: path.join(inputs.resourcesPath, 'server'),
      frontendDir: path.join(inputs.resourcesPath, 'frontend'),
    }
  }
  return {
    pythonExe:
      inputs.pythonOverride ?? path.join(inputs.repoRoot, 'server', '.venv', 'Scripts', 'python.exe'),
    serverDir: path.join(inputs.repoRoot, 'server'),
    frontendDir: path.join(inputs.repoRoot, 'dist'),
  }
}
```

- [ ] **Step 4: 运行测试确认通过**

Run（在 `desktop/` 目录）: `npm test`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add desktop/src/paths.ts desktop/tests/paths.spec.ts
git commit -m "feat(desktop): resolve bundled/dev backend resource paths"
```

---

### Task 6: 后端子进程管理

**Files:**
- Create: `desktop/src/backend.ts`
- Test: `desktop/tests/backend.spec.ts`

- [ ] **Step 1: 写失败测试**

创建 `desktop/tests/backend.spec.ts`：

```ts
import { afterEach, describe, expect, it, vi } from 'vitest'

import { BackendProcess } from '../src/backend'
import type { BackendPaths } from '../src/paths'

const PATHS: BackendPaths = {
  pythonExe: 'C:/py/python.exe',
  serverDir: 'C:/app/server',
  frontendDir: 'C:/app/frontend',
}

function fakeChild() {
  return { killed: false, kill: vi.fn(), stderr: null } as never
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('BackendProcess', () => {
  it('spawns the backend with port/data-dir/frontend-dir args', () => {
    const spawnFn = vi.fn(() => fakeChild())
    const proc = new BackendProcess(PATHS, spawnFn as never)
    const { url } = proc.start({ port: 9123, dataDir: 'D:/data' })

    expect(url).toBe('http://127.0.0.1:9123')
    const [exe, args, opts] = spawnFn.mock.calls[0] as unknown as [
      string,
      string[],
      { cwd: string; env: Record<string, string> },
    ]
    expect(exe).toBe(PATHS.pythonExe)
    expect(args).toEqual(expect.arrayContaining(['-m', 'app.main', '--port', '9123']))
    expect(args).toEqual(expect.arrayContaining(['--data-dir', 'D:/data']))
    expect(args).toEqual(expect.arrayContaining(['--frontend-dir', PATHS.frontendDir]))
    expect(opts.cwd).toBe(PATHS.serverDir)
    expect(opts.env.PYTHONNOUSERSITE).toBe('1')
    expect(opts.env.PYTHONPATH).toBe(PATHS.serverDir)
  })

  it('resolves once /ready returns ok', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true })
    vi.stubGlobal('fetch', fetchMock)
    const proc = new BackendProcess(PATHS, vi.fn(() => fakeChild()) as never)

    await proc.waitReady('http://127.0.0.1:9123', 1000, 10)
    expect(fetchMock).toHaveBeenCalledWith('http://127.0.0.1:9123/ready')
  })

  it('throws when /ready never succeeds before the deadline', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('econnrefused')))
    const proc = new BackendProcess(PATHS, vi.fn(() => fakeChild()) as never)

    await expect(proc.waitReady('http://127.0.0.1:9123', 30, 10)).rejects.toThrow(
      '后端启动超时',
    )
  })

  it('stops the child process', () => {
    const child = fakeChild() as unknown as { kill: ReturnType<typeof vi.fn> }
    const proc = new BackendProcess(PATHS, vi.fn(() => child) as never)
    proc.start({ port: 9123, dataDir: 'D:/data' })
    proc.stop()
    expect(child.kill).toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run（在 `desktop/` 目录）: `npm test`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 `BackendProcess`**

创建 `desktop/src/backend.ts`：

```ts
import { spawn, type ChildProcess } from 'node:child_process'

import type { BackendPaths } from './paths'

export interface BackendStartOptions {
  port: number
  dataDir: string
}

export interface BackendHandle {
  child: ChildProcess
  url: string
}

type SpawnFn = typeof spawn

export class BackendProcess {
  private child: ChildProcess | null = null

  constructor(
    private readonly paths: BackendPaths,
    private readonly spawnFn: SpawnFn = spawn,
  ) {}

  start(options: BackendStartOptions): BackendHandle {
    const url = `http://127.0.0.1:${options.port}`
    const args = [
      '-m',
      'app.main',
      '--port',
      String(options.port),
      '--data-dir',
      options.dataDir,
      '--frontend-dir',
      this.paths.frontendDir,
    ]
    const child = this.spawnFn(this.paths.pythonExe, args, {
      cwd: this.paths.serverDir,
      env: {
        ...process.env,
        PYTHONPATH: this.paths.serverDir,
        PYTHONNOUSERSITE: '1',
      },
      stdio: ['ignore', 'pipe', 'pipe'],
    })
    this.child = child
    return { child, url }
  }

  /** 轮询 /ready 直到核心 bootstrap 完成（SQLite + 日记 CRUD 可用）。 */
  async waitReady(url: string, timeoutMs = 90_000, intervalMs = 250): Promise<void> {
    const deadline = Date.now() + timeoutMs
    while (Date.now() < deadline) {
      try {
        const response = await fetch(`${url}/ready`)
        if (response.ok) return
      } catch {
        // 后端尚未监听，继续轮询
      }
      await new Promise((resolve) => setTimeout(resolve, intervalMs))
    }
    throw new Error('后端启动超时')
  }

  stop(): void {
    if (this.child && !this.child.killed) {
      this.child.kill()
    }
    this.child = null
  }
}
```

- [ ] **Step 4: 运行测试确认通过**

Run（在 `desktop/` 目录）: `npm test`
Expected: 7 passed

- [ ] **Step 5: 提交**

```bash
git add desktop/src/backend.ts desktop/tests/backend.spec.ts
git commit -m "feat(desktop): spawn + health-check the local backend sidecar"
```

---

### Task 7: preload 注入后端地址

**Files:**
- Create: `desktop/src/argv.ts`
- Create: `desktop/src/preload.ts`
- Test: `desktop/tests/argv.spec.ts`

- [ ] **Step 1: 写失败测试**

创建 `desktop/tests/argv.spec.ts`：

```ts
import { describe, expect, it } from 'vitest'

import { parseBackendUrl } from '../src/argv'

describe('parseBackendUrl', () => {
  it('extracts the backend url from additionalArguments', () => {
    const argv = ['electron', '--backend-url=http://127.0.0.1:9123', '--other']
    expect(parseBackendUrl(argv)).toBe('http://127.0.0.1:9123')
  })

  it('returns undefined when absent', () => {
    expect(parseBackendUrl(['electron'])).toBeUndefined()
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run（在 `desktop/` 目录）: `npm test`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 `parseBackendUrl` 与 preload**

创建 `desktop/src/argv.ts`：

```ts
const PREFIX = '--backend-url='

export function parseBackendUrl(argv: readonly string[]): string | undefined {
  const hit = argv.find((arg) => arg.startsWith(PREFIX))
  return hit ? hit.slice(PREFIX.length) : undefined
}
```

创建 `desktop/src/preload.ts`：

```ts
import { contextBridge } from 'electron'

import { parseBackendUrl } from './argv'

const backendUrl = parseBackendUrl(process.argv)

if (backendUrl) {
  contextBridge.exposeInMainWorld('__NIGHT_DIARY__', { backendUrl })
}
```

- [ ] **Step 4: 运行测试确认通过**

Run（在 `desktop/` 目录）: `npm test`
Expected: 9 passed

- [ ] **Step 5: 提交**

```bash
git add desktop/src/argv.ts desktop/src/preload.ts desktop/tests/argv.spec.ts
git commit -m "feat(desktop): inject backend url into the renderer via preload"
```

---

### Task 8: Electron 主进程编排

**Files:**
- Create: `desktop/src/main.ts`

> 说明：`main.ts` 是薄胶水（依赖 electron 运行时），由 Task 11 的冒烟测试覆盖；其可测逻辑已抽到 Task 4–7 的纯函数中。

- [ ] **Step 1: 实现 `main.ts`**

创建 `desktop/src/main.ts`：

```ts
import path from 'node:path'

import { app, BrowserWindow } from 'electron'

import { BackendProcess } from './backend'
import { resolveBackendPaths } from './paths'
import { findFreePort } from './port'

const backend = new BackendProcess(
  resolveBackendPaths({
    packaged: app.isPackaged,
    resourcesPath: process.resourcesPath,
    repoRoot: path.resolve(__dirname, '..', '..'),
    pythonOverride: process.env.NIGHT_DIARY_PYTHON,
  }),
)

let mainWindow: BrowserWindow | null = null

async function boot(): Promise<void> {
  const port = await findFreePort()
  const dataDir = path.join(app.getPath('appData'), 'night-diary')

  const { child, url } = backend.start({ port, dataDir })
  child.stderr?.on('data', (chunk) => console.error('[backend]', String(chunk)))
  child.on('exit', (code) => {
    if (code !== 0 && code !== null) {
      console.error(`[backend] exited unexpectedly with code ${code}`)
    }
  })

  await backend.waitReady(url)

  mainWindow = new BrowserWindow({
    width: 1100,
    height: 760,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: '#FAF7F3',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      additionalArguments: [`--backend-url=${url}`],
    },
  })
  await mainWindow.loadURL(url)
}

app.whenReady().then(boot).catch((error) => {
  console.error('[desktop] boot failed:', error)
  app.quit()
})

app.on('window-all-closed', () => {
  backend.stop()
  app.quit()
})

app.on('before-quit', () => {
  backend.stop()
})
```

- [ ] **Step 2: 编译**

Run（在 `desktop/` 目录）: `npm run build`
Expected: 生成 `desktop/dist/{main,preload,backend,paths,port,argv}.js`，无类型错误

- [ ] **Step 3: 提交**

```bash
git add desktop/src/main.ts
git commit -m "feat(desktop): electron main process orchestration"
```

---

## Phase C — Python 运行时与端到端冒烟

### Task 9: uv 构建可重定位 Python 运行时

**Files:**
- Create: `desktop/scripts/build-runtime.ps1`
- Create: `desktop/requirements-runtime.txt`

- [ ] **Step 1: 固定运行时依赖清单**

在 `server/` 目录用 uv 从 `pyproject.toml` 的**核心依赖**（不含 `[dev]`/`[eval]`）编译出锁定清单：

Run（在 `server/` 目录）: `uv pip compile pyproject.toml -o ../desktop/requirements-runtime.txt`
Expected: 生成 `desktop/requirements-runtime.txt`，其中**不含** `torch` / `sentence-transformers`

- [ ] **Step 2: 写运行时构建脚本**

创建 `desktop/scripts/build-runtime.ps1`：

```powershell
# 构建可重定位的 Python 运行时（python-build-standalone + 依赖），
# 输出到 desktop/resources/runtime，供 electron-builder 作为 extraResources 打包。
# 不使用 PyInstaller —— 目录式运行时规避 onnxruntime/chromadb 的原生依赖冻结问题。
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktop = Split-Path -Parent $here
$repo = Split-Path -Parent $desktop
$runtimeDir = Join-Path $desktop 'resources\runtime'
$req = Join-Path $desktop 'requirements-runtime.txt'

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  throw "未找到 uv。请先安装：https://docs.astral.sh/uv/getting-started/installation/"
}

# 1) 安装可重定位的独立 CPython 到指定目录（python-build-standalone）
$env:UV_PYTHON_INSTALL_DIR = $runtimeDir
uv python install 3.11 --install-dir $runtimeDir

# 2) 解析刚安装的 python 可执行文件
$pythonExe = Get-ChildItem -Path $runtimeDir -Recurse -Filter python.exe |
  Select-Object -First 1 -ExpandProperty FullName
if (-not $pythonExe) { throw "运行时 python.exe 未找到：$runtimeDir" }

# 3) 安装运行时依赖（不装 torch / sentence-transformers）
uv pip install --python $pythonExe -r $req

# 4) 验证：核心包可导入
& $pythonExe -c "import fastapi, uvicorn, sqlalchemy, chromadb; print('runtime ok')"

Write-Host "Runtime built at $runtimeDir using $pythonExe"
```

- [ ] **Step 3: 运行脚本构建运行时**

Run（在仓库根）: `powershell -ExecutionPolicy Bypass -File desktop/scripts/build-runtime.ps1`
Expected: 末尾输出 `runtime ok` 与 `Runtime built at ...`

- [ ] **Step 4: 验证运行时不含重型 ML**

Run: `Get-ChildItem desktop/resources/runtime -Recurse -Directory | Where-Object { $_.Name -in @('torch','sentence_transformers') }`
Expected: 无输出（确认未打包 torch/sentence-transformers）

- [ ] **Step 5: 提交**

```bash
git add desktop/scripts/build-runtime.ps1 desktop/requirements-runtime.txt
git commit -m "build(desktop): relocatable python runtime via uv (no pyinstaller)"
```

> `desktop/resources/` 属构建产物，已在 Task 10 加入 `.gitignore`，此处不提交。

---

### Task 10: 端到端冒烟（开发态）

**Files:**
- Create: `desktop/scripts/smoke.ps1`

- [ ] **Step 1: 写冒烟脚本**

创建 `desktop/scripts/smoke.ps1`：

```powershell
# 开发态冒烟：构建前端 + 编译 Electron 宿主 + 用本地 venv 起后端并打开窗口。
# 人工确认：窗口打开后能登录、能新建一篇日记。
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktop = Split-Path -Parent $here
$repo = Split-Path -Parent $desktop

# 1) 构建前端（产出 dist/，由后端静态托管）
Push-Location $repo
npm run build
Pop-Location

# 2) 编译 Electron 宿主
Push-Location $desktop
npm run build

# 3) 指向本地 venv 的 python，启动 Electron（main 会 spawn 后端并开窗）
$env:NIGHT_DIARY_PYTHON = Join-Path $repo 'server\.venv\Scripts\python.exe'
npx electron .
Pop-Location
```

- [ ] **Step 2: 运行冒烟并人工验证**

Run（在仓库根）: `powershell -ExecutionPolicy Bypass -File desktop/scripts/smoke.ps1`
Expected（人工确认清单）：
1. 出现原生窗口（非浏览器），无地址栏；
2. 窗口加载后显示夜记界面；
3. 打开 DevTools 控制台无 CORS 报错；
4. 能注册/登录、新建并保存一篇日记；
5. 关闭窗口后，任务管理器无残留 `python.exe` 进程（`backend.stop()` 生效）。

- [ ] **Step 3: 提交**

```bash
git add desktop/scripts/smoke.ps1
git commit -m "test(desktop): dev-mode end-to-end smoke script"
```

---

## Phase D — 打包与交付

### Task 11: electron-builder（Windows NSIS 安装包）

**Files:**
- Create: `desktop/electron-builder.yml`
- Modify: `.gitignore`

- [ ] **Step 1: 写打包配置**

创建 `desktop/electron-builder.yml`：

```yaml
appId: com.nightdiary.desktop
productName: Night Diary
directories:
  output: release
files:
  - dist/**/*
  - package.json
extraResources:
  - from: resources/runtime
    to: runtime
  - from: ../server
    to: server
    filter:
      - "**/*"
      - "!**/__pycache__/**"
      - "!**/.venv/**"
      - "!**/tests/**"
      - "!**/.pytest_cache/**"
  - from: ../dist
    to: frontend
win:
  target:
    - nsis
  artifactName: NightDiary-${version}-setup.${ext}
nsis:
  oneClick: false
  perMachine: false
  allowToChangeInstallationDirectory: true
  createDesktopShortcut: true
  shortcutName: 夜记
```

- [ ] **Step 2: 更新 `.gitignore`**

在 `.gitignore` 末尾追加：

```
# Desktop (Electron) build artifacts
desktop/node_modules/
desktop/dist/
desktop/resources/
desktop/release/
```

- [ ] **Step 3: 打包**

Run（在 `desktop/` 目录，需先完成 Task 9 的运行时构建）:
```
npm run build
npx electron-builder --win nsis --config electron-builder.yml
```
Expected: 生成 `desktop/release/NightDiary-0.1.0-setup.exe`

- [ ] **Step 4: 验证安装包**

Run: `Get-ChildItem desktop/release -Filter *.exe`
Expected: 存在 `NightDiary-0.1.0-setup.exe`

- [ ] **Step 5: 提交**

```bash
git add desktop/electron-builder.yml .gitignore
git commit -m "build(desktop): NSIS installer config for windows x64"
```

---

### Task 12: 一键构建脚本与文档

**Files:**
- Create: `desktop/scripts/build-all.ps1`
- Modify: `README.md`

- [ ] **Step 1: 写一键构建脚本**

创建 `desktop/scripts/build-all.ps1`：

```powershell
# 一键：前端构建 → Python 运行时 → Electron 编译 → NSIS 打包
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktop = Split-Path -Parent $here
$repo = Split-Path -Parent $desktop

Write-Host '== 1/4 build frontend =='
Push-Location $repo; npm run build; Pop-Location

Write-Host '== 2/4 build python runtime =='
& (Join-Path $here 'build-runtime.ps1')

Write-Host '== 3/4 compile electron host =='
Push-Location $desktop; npm run build; Pop-Location

Write-Host '== 4/4 package NSIS installer =='
Push-Location $desktop
npx electron-builder --win nsis --config electron-builder.yml
Pop-Location

Write-Host '== done: desktop/release/NightDiary-*-setup.exe =='
```

- [ ] **Step 2: 更新 README**

在 `README.md` 的「本地开发（无 Docker）」小节之后新增：

````markdown
### 桌面版（Windows，双击即用）

桌面版用 Electron 宿主自动启动本地后端，并把界面装进原生窗口——无需 Docker、无需手动开浏览器。

```powershell
# 开发态运行（复用本地 venv 的后端）
powershell -ExecutionPolicy Bypass -File desktop/scripts/smoke.ps1

# 构建安装包（产出 desktop/release/NightDiary-<version>-setup.exe）
powershell -ExecutionPolicy Bypass -File desktop/scripts/build-all.ps1
```

- Python 运行时由 `uv` + `python-build-standalone` 以可重定位目录交付，**不使用 PyInstaller**。
- 运行时**不含 torch**：embedding/rerank 走云端（设置页配置 `EMBEDDING_API_KEY` / `RERANK_API_KEY`）。
- 数据目录：`%APPDATA%/night-diary`（与后端 `data_dir` 默认一致）。
````

- [ ] **Step 3: 提交**

```bash
git add desktop/scripts/build-all.ps1 README.md
git commit -m "docs(desktop): one-shot build script and README desktop section"
```

---

## 验证清单（全部完成后逐项确认）

- [ ] 后端全量单测：`cd server && .\.venv\Scripts\python.exe -m pytest tests/unit -q` → 全绿（含新增 static mount 用例）
- [ ] 后端 ruff + mypy：`ruff check app tests` / `mypy app` → 无告警
- [ ] 前端全量测试：`npx vitest run` → 全绿（含新增 `useBackend.spec.ts`）
- [ ] 前端类型/lint：`npm run type-check` / `npm run lint` → 无错误
- [ ] 桌面单测：`cd desktop && npm test` → 全绿
- [ ] 冒烟：`desktop/scripts/smoke.ps1` → 原生窗口可用、无 CORS 报错、关闭无残留 python 进程
- [ ] 安装包：`desktop/release/NightDiary-*-setup.exe` 存在，安装后双击可启动
- [ ] 无回归：现有 Docker 路径（`docker compose up -d` → `http://localhost`）不受影响

## 风险与后续

| 风险 | 缓解 |
|---|---|
| `uv python install --install-dir` 参数在旧版 uv 上缺失 | 脚本第 1 步失败时改用 `UV_PYTHON_INSTALL_DIR` 环境变量（脚本已同时设置）；或升级 uv |
| Windows 缺少 WebView2 | Electron 自带 Chromium，**不依赖 WebView2**（这是选 Electron 而非 Tauri 的原因之一） |
| 无云端 embedding key 时 RAG 退化 | 核心运行时不装 sentence-transformers，`build_embedding_function` 应优雅降级；在冒烟清单中确认日记 CRUD 仍可用 |
| 安装包未签名导致 SmartScreen 警告 | 后续 PR 引入代码签名证书；本期先接受警告（与 DSH Desktop 早期一致） |
| 首次启动后端 bootstrap 慢 | `waitReady` 90s 超时 + `/ready` 探针；必要时后续加启动画面 |

**后续 PR（本期不做）**：自动更新（electron-updater）、启动画面与进度条、代码签名、macOS/Linux 打包、本地模型按需下载（若确实需要离线 RAG）。