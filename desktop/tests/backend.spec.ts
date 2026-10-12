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