/**
 * Dev wrapper: start a managed FastAPI sidecar, run `tauri dev`, stop backend on exit.
 *
 * Attach-only mode (do not start/stop backend): NIGHTDIARY_DEV_BACKEND_ATTACH=1
 */
import { spawn } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  killPortOccupant,
  killProcessTree,
  probeHealth,
  startManagedBackend,
  waitForHealth,
} from './lib/dev-backend.mjs'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.join(__dirname, '..')
const PORT = Number(process.env.NIGHTDIARY_DEV_BACKEND || 8000)
const VITE_PORT = Number(process.env.NIGHTDIARY_VITE_PORT || 5173)
const ATTACH_ONLY = process.env.NIGHTDIARY_DEV_BACKEND_ATTACH === '1'

let backendChild = null
let tauriChild = null
let shuttingDown = false

function stopBackend() {
  if (!backendChild?.pid) return
  console.log('[dev-backend] stopping managed sidecar…')
  killProcessTree(backendChild.pid)
  backendChild = null
}

async function ensureBackend() {
  if (ATTACH_ONLY) {
    if (await probeHealth(PORT)) {
      console.log(`[dev-backend] attach mode: using existing backend on ${PORT}`)
      return
    }
    console.error(
      `[dev-backend] attach mode: nothing listening on ${PORT}. Start it first:\n` +
        `  cd server && python -m uvicorn app.main:app --reload --host 127.0.0.1 --port ${PORT}`,
    )
    process.exit(1)
  }

  if (await probeHealth(PORT)) {
    killPortOccupant(PORT, 'dev-backend')
    await new Promise((resolve) => setTimeout(resolve, 400))
  }

  console.log(`[dev-backend] starting managed sidecar on ${PORT} with --reload…`)
  backendChild = startManagedBackend(PORT)

  backendChild.on('exit', (code, signal) => {
    if (shuttingDown) return
    console.error(`[dev-backend] sidecar exited unexpectedly (code=${code ?? 'null'}, signal=${signal ?? 'null'})`)
    shutdown(1)
  })

  if (!(await waitForHealth(PORT))) {
    console.error(`[dev-backend] timed out waiting for /health on ${PORT}`)
    shutdown(1)
  }

  console.log(`[dev-backend] ready on http://127.0.0.1:${PORT}`)
}

async function ensureVitePortFree() {
  killPortOccupant(VITE_PORT, 'dev-vite')
  await new Promise((resolve) => setTimeout(resolve, 400))
}

function runTauriDev() {
  const tauriCli = path.join(ROOT, 'node_modules', '@tauri-apps', 'cli', 'tauri.js')
  tauriChild = spawn(process.execPath, [tauriCli, 'dev'], {
    cwd: ROOT,
    stdio: 'inherit',
    env: process.env,
  })

  tauriChild.on('exit', (code, signal) => {
    if (shuttingDown) return
    const exitCode = code ?? (signal ? 1 : 0)
    shutdown(exitCode)
  })
}

function shutdown(exitCode = 0) {
  if (shuttingDown) return
  shuttingDown = true

  if (tauriChild && !tauriChild.killed) {
    killProcessTree(tauriChild.pid)
    tauriChild = null
  }

  killPortOccupant(VITE_PORT, 'dev-vite')

  if (!ATTACH_ONLY) {
    stopBackend()
  }

  process.exit(exitCode)
}

for (const signal of ['SIGINT', 'SIGTERM', 'SIGHUP']) {
  process.on(signal, () => {
    console.log(`\n[dev-tauri] received ${signal}, shutting down…`)
    shutdown(signal === 'SIGINT' ? 130 : 0)
  })
}

await ensureBackend()
await ensureVitePortFree()
runTauriDev()
