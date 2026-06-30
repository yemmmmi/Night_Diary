/**
 * Full desktop build pipeline: PyInstaller onedir + Tauri NSIS bundle.
 *
 * Usage: node scripts/build-desktop.mjs
 */
import { existsSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.join(__dirname, '..')

function run(cmd, args, cwd = ROOT) {
  console.log(`\n> ${cmd} ${args.join(' ')}`)
  const result = spawnSync(cmd, args, { cwd, stdio: 'inherit', shell: true })
  if (result.status !== 0) {
    console.error(`Command failed with exit code ${result.status}`)
    process.exit(result.status ?? 1)
  }
}

// 1. Build frontend
run('npm', ['run', 'build'])

// 2. Build PyInstaller onedir sidecar
const python = process.env.PYTHON_EXE || 'python'
run(python, ['-m', 'PyInstaller', '--noconfirm', 'server/build.spec'])

// 3. Prepare sidecar for Tauri bundling
const onedirDir = path.join(ROOT, 'dist', 'nightdiary-backend')

if (!existsSync(onedirDir)) {
  console.error(`PyInstaller output not found: ${onedirDir}`)
  process.exit(1)
}

run('node', ['scripts/prepare-sidecar.mjs'])

// 4. Build Tauri NSIS installer
run('npm', ['run', 'tauri', 'build'])
