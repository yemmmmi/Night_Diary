/**
 * Dev-only: keep a persistent FastAPI sidecar on port 8000 so `npm run tauri dev`
 * attaches instantly instead of cold-spawning Python on every Tauri restart.
 */
import { spawn } from 'node:child_process'
import http from 'node:http'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const SERVER_DIR = path.join(__dirname, '..', 'server')
const PORT = Number(process.env.NIGHTDIARY_DEV_BACKEND || 8000)

function probeHealth() {
  return new Promise((resolve) => {
    const req = http.get(`http://127.0.0.1:${PORT}/health`, (res) => {
      res.resume()
      resolve(res.statusCode === 200)
    })
    req.on('error', () => resolve(false))
    req.setTimeout(400, () => {
      req.destroy()
      resolve(false)
    })
  })
}

async function waitForHealth(maxMs = 120_000, intervalMs = 150) {
  const deadline = Date.now() + maxMs
  while (Date.now() < deadline) {
    if (await probeHealth()) return true
    await new Promise((resolve) => setTimeout(resolve, intervalMs))
  }
  return false
}

if (await probeHealth()) {
  console.log(`[dev-backend] already listening on ${PORT}`)
  process.exit(0)
}

console.log(`[dev-backend] starting Python sidecar on ${PORT}…`)
const python = process.platform === 'win32' ? 'python' : 'python3'
const child = spawn(
  python,
  ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(PORT)],
  {
    cwd: SERVER_DIR,
    detached: true,
    stdio: 'ignore',
    env: {
      ...process.env,
      PYTHONUNBUFFERED: '1',
      NO_PROXY: '127.0.0.1,localhost',
      no_proxy: '127.0.0.1,localhost',
      HTTP_PROXY: '',
      HTTPS_PROXY: '',
    },
  },
)
child.unref()

if (!(await waitForHealth())) {
  console.error(`[dev-backend] timed out waiting for /health on ${PORT}`)
  process.exit(1)
}

console.log(`[dev-backend] ready on http://127.0.0.1:${PORT}`)
