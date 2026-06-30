/**
 * Copy PyInstaller ONEDIR output into src-tauri/resources/ for Tauri bundling.
 *
 * ONEDIR layout: dist/nightdiary-backend/nightdiary-backend.exe (+ _internal/)
 * Tauri bundles the entire directory as resources.
 *
 * Usage (from repo root, after `python -m PyInstaller server/build.spec`):
 *   node scripts/prepare-sidecar.mjs
 */
import { cpSync, existsSync, mkdirSync, rmSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.join(__dirname, '..')

const onedirDir = path.join(ROOT, 'dist', 'nightdiary-backend')
const destDir = path.join(ROOT, 'src-tauri', 'resources', 'nightdiary-backend')

if (!existsSync(onedirDir)) {
  console.error(`PyInstaller onedir output not found: ${onedirDir}`)
  console.error('Run: python -m PyInstaller server/build.spec')
  process.exit(1)
}

if (existsSync(destDir)) {
  rmSync(destDir, { recursive: true, force: true })
}
mkdirSync(destDir, { recursive: true })
cpSync(onedirDir, destDir, { recursive: true, force: true })
console.log(`Copied onedir sidecar → ${destDir}`)
