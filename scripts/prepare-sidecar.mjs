/**
 * Copy PyInstaller output into src-tauri/binaries/ for Tauri externalBin bundling.
 *
 * Usage (from repo root, after `pyinstaller server/build.spec`):
 *   node scripts/prepare-sidecar.mjs
 */
import { copyFileSync, existsSync, mkdirSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.join(__dirname, '..')

const triple = process.env.TAURI_TARGET_TRIPLE ?? 'x86_64-pc-windows-msvc'
const isWindows = triple.includes('windows')
const sidecarName = isWindows ? 'nightdiary-backend.exe' : 'nightdiary-backend'
const src = path.join(ROOT, 'dist', sidecarName)
const destDir = path.join(ROOT, 'src-tauri', 'binaries')
const dest = path.join(destDir, `nightdiary-backend-${triple}${isWindows ? '.exe' : ''}`)

if (!existsSync(src)) {
  console.error(`Sidecar not found: ${src}`)
  console.error('Run: pyinstaller server/build.spec')
  process.exit(1)
}

mkdirSync(destDir, { recursive: true })
copyFileSync(src, dest)
console.log(`Copied sidecar → ${dest}`)
