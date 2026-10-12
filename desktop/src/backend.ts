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