import { invoke } from '@tauri-apps/api/core'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import {
  resetCoreReady,
  resolveBackendBaseUrl,
  waitForBackendHealth,
  waitForCoreReady,
} from '../useBackend'

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}))

vi.mock('@tauri-apps/api/event', () => ({
  listen: vi.fn(),
}))

import { listen } from '@tauri-apps/api/event'

describe('useBackend helpers', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.unstubAllGlobals()
    resetCoreReady()
  })

  it('resolveBackendBaseUrl uses Tauri port when invoke succeeds', async () => {
    vi.mocked(invoke).mockResolvedValue(19042)
    await expect(resolveBackendBaseUrl()).resolves.toBe('http://127.0.0.1:19042')
  })

  it('resolveBackendBaseUrl falls back when not in Tauri', async () => {
    vi.mocked(invoke).mockRejectedValue(new Error('not tauri'))
    await expect(resolveBackendBaseUrl()).resolves.toBe('http://127.0.0.1:8000')
  })

  it('waitForBackendHealth succeeds via Tauri is_backend_ready', async () => {
    vi.stubGlobal('__TAURI_INTERNALS__', {})
    vi.mocked(invoke).mockImplementation((cmd: string) => {
      if (cmd === 'is_backend_ready') {
        return Promise.resolve(true)
      }
      return Promise.reject(new Error(`unexpected: ${cmd}`))
    })
    await expect(waitForBackendHealth('http://127.0.0.1:1')).resolves.toBeUndefined()
    expect(invoke).toHaveBeenCalledWith('is_backend_ready')
    expect(listen).not.toHaveBeenCalled()
  })

  it('waitForBackendHealth resolves on Tauri backend-ready event', async () => {
    vi.stubGlobal('__TAURI_INTERNALS__', {})
    vi.mocked(invoke).mockImplementation((cmd: string) => {
      if (cmd === 'is_backend_ready') {
        return Promise.resolve(false)
      }
      return Promise.reject(new Error(`unexpected: ${cmd}`))
    })
    vi.mocked(listen).mockImplementation(async (_event, handler) => {
      setTimeout(() => {
        ;(handler as (event: { payload: number }) => void)({ payload: 1 })
      }, 5)
      return () => undefined
    })

    await expect(waitForBackendHealth('http://127.0.0.1:1', 10, 10)).resolves.toBeUndefined()
    expect(listen).toHaveBeenCalledWith('backend-ready', expect.any(Function))
  })

  it('waitForBackendHealth falls back to fetch when invoke unavailable', async () => {
    vi.mocked(invoke).mockRejectedValue(new Error('not tauri'))
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, status: 200 }),
    )
    await expect(waitForBackendHealth('http://127.0.0.1:1')).resolves.toBeUndefined()
  })

  it('waitForBackendHealth throws after max attempts', async () => {
    vi.stubGlobal('__TAURI_INTERNALS__', {})
    vi.mocked(invoke).mockImplementation((cmd: string) => {
      if (cmd === 'is_backend_ready') {
        return Promise.resolve(false)
      }
      return Promise.reject(new Error(`unexpected: ${cmd}`))
    })
    vi.mocked(listen).mockResolvedValue(() => undefined)
    await expect(
      waitForBackendHealth('http://127.0.0.1:1', 2, 5),
    ).rejects.toThrow('Backend health check timed out')
  })

  it('waitForCoreReady resolves when /ready returns ok', async () => {
    vi.mocked(invoke).mockRejectedValue(new Error('not tauri'))
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, status: 200 }),
    )
    await expect(waitForCoreReady('http://127.0.0.1:8000', 1000)).resolves.toBeUndefined()
  })
})
