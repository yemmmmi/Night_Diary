/**
 * Ensure a sidecar binary exists for `cargo check` / `tauri dev` when PyInstaller
 * output is absent. Copies cmd.exe as a compile-time placeholder only.
 */
import { copyFileSync, existsSync, mkdirSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.join(__dirname, '..')
const triple = process.env.TAURI_TARGET_TRIPLE ?? 'x86_64-pc-windows-msvc'
const destDir = path.join(ROOT, 'src-tauri', 'binaries')
const dest = path.join(destDir, `nightdiary-backend-${triple}.exe`)

if (existsSync(dest)) {
  process.exit(0)
}

const realSidecar = path.join(ROOT, 'dist', 'nightdiary-backend.exe')
if (existsSync(realSidecar)) {
  mkdirSync(destDir, { recursive: true })
  copyFileSync(realSidecar, dest)
  console.log(`[ensure-sidecar-stub] copied real sidecar → ${dest}`)
  process.exit(0)
}

if (process.platform === 'win32') {
  const stub = path.join(process.env.SystemRoot ?? 'C:\\Windows', 'System32', 'cmd.exe')
  if (existsSync(stub)) {
    mkdirSync(destDir, { recursive: true })
    copyFileSync(stub, dest)
    console.warn(`[ensure-sidecar-stub] using cmd.exe placeholder → ${dest}`)
    process.exit(0)
  }
}

console.error('No sidecar or Windows stub available. Run: make build-sidecar')
process.exit(1)
