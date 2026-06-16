/**
 * npm run tauri <cmd> — routes `dev` through the managed backend wrapper.
 */
import { spawn, spawnSync } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.join(__dirname, '..')
const TAURI_CLI = path.join(ROOT, 'node_modules', '@tauri-apps', 'cli', 'tauri.js')
const args = process.argv.slice(2)

/** Tauri compile needs externalBin on disk; Vite `npm run build` does not. */
function ensureSidecarStub() {
  const result = spawnSync(process.execPath, [path.join(__dirname, 'ensure-sidecar-stub.mjs')], {
    cwd: ROOT,
    stdio: 'inherit',
  })
  if (result.status !== 0) {
    process.exit(result.status ?? 1)
  }
}

if (args[0] === 'dev' || args[0] === 'build') {
  ensureSidecarStub()
}

if (args[0] === 'dev') {
  const child = spawn(process.execPath, [path.join(__dirname, 'dev-tauri.mjs')], {
    cwd: ROOT,
    stdio: 'inherit',
    env: process.env,
  })
  child.on('exit', (code, signal) => {
    process.exit(code ?? (signal ? 1 : 0))
  })
} else {
  const child = spawn(process.execPath, [TAURI_CLI, ...args], {
    cwd: ROOT,
    stdio: 'inherit',
    env: process.env,
  })
  child.on('exit', (code, signal) => {
    process.exit(code ?? (signal ? 1 : 0))
  })
}
