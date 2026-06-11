import { execSync, spawn } from 'node:child_process'
import http from 'node:http'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
export const SERVER_DIR = path.join(__dirname, '..', '..', 'server')

export function backendEnv() {
  return {
    ...process.env,
    PYTHONUNBUFFERED: '1',
    NO_PROXY: '127.0.0.1,localhost,api.deepseek.com',
    no_proxy: '127.0.0.1,localhost,api.deepseek.com',
    HTTP_PROXY: '',
    HTTPS_PROXY: '',
  }
}

export function probeHealth(port) {
  return new Promise((resolve) => {
    const req = http.get(`http://127.0.0.1:${port}/health`, (res) => {
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

export async function waitForHealth(port, maxMs = 120_000, intervalMs = 150) {
  const deadline = Date.now() + maxMs
  while (Date.now() < deadline) {
    if (await probeHealth(port)) return true
    await new Promise((resolve) => setTimeout(resolve, intervalMs))
  }
  return false
}

function parseListeningPid(port) {
  if (process.platform === 'win32') {
    let out = ''
    try {
      out = execSync(`netstat -ano | findstr :${port}`, { encoding: 'utf8', stdio: ['pipe', 'pipe', 'ignore'] })
    } catch {
      return null
    }
    for (const line of out.split(/\r?\n/)) {
      if (!line.includes('LISTENING')) continue
      const parts = line.trim().split(/\s+/)
      const pid = Number(parts.at(-1))
      if (Number.isInteger(pid) && pid > 0) return pid
    }
    return null
  }

  try {
    const out = execSync(`lsof -ti tcp:${port} -sTCP:LISTEN`, { encoding: 'utf8', stdio: ['pipe', 'pipe', 'ignore'] })
    const pid = Number(out.trim().split(/\s+/)[0])
    return Number.isInteger(pid) && pid > 0 ? pid : null
  } catch {
    return null
  }
}

export function killProcessTree(pid) {
  if (!pid || pid === process.pid) return

  if (process.platform === 'win32') {
    try {
      execSync(`taskkill /PID ${pid} /T /F`, { stdio: 'ignore' })
    } catch {
      // process may already be gone
    }
    return
  }

  try {
    process.kill(-pid, 'SIGTERM')
  } catch {
    try {
      process.kill(pid, 'SIGTERM')
    } catch {
      // ignore
    }
  }
}

export function killPortOccupant(port, label = 'dev') {
  const pid = parseListeningPid(port)
  if (pid) {
    console.log(`[${label}] stopping existing listener on ${port} (pid ${pid})`)
    killProcessTree(pid)
  }
}

export function startManagedBackend(port) {
  const python = process.platform === 'win32' ? 'python' : 'python3'
  return spawn(
    python,
    ['-m', 'uvicorn', 'app.main:app', '--reload', '--host', '127.0.0.1', '--port', String(port)],
    {
      cwd: SERVER_DIR,
      stdio: 'inherit',
      env: backendEnv(),
    },
  )
}
