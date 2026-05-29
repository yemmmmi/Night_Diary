import { invoke } from '@tauri-apps/api/core'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import {
  resolveBackendBaseUrl,
  waitForBackendHealth,
} from '../useBackend'

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}))

describe('useBackend helpers', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('resolveBackendBaseUrl uses Tauri port when invoke succeeds', async () => {
    vi.mocked(invoke).mockResolvedValue(19042)
    await expect(resolveBackendBaseUrl()).resolves.toBe('http://127.0.0.1:19042')
  })

  it('resolveBackendBaseUrl falls back when not in Tauri', async () => {
    vi.mocked(invoke).mockRejectedValue(new Error('not tauri'))
    await expect(resolveBackendBaseUrl()).resolves.toBe('http://127.0.0.1:8000')
  })

  it('waitForBackendHealth succeeds via Tauri invoke', async () => {
    vi.mocked(invoke).mockImplementation((cmd: string) => {
      if (cmd === 'check_backend_health') {
        return Promise.resolve(true)
      }
      return Promise.reject(new Error(`unexpected: ${cmd}`))
    })
    await expect(waitForBackendHealth('http://127.0.0.1:1')).resolves.toBeUndefined()
    expect(invoke).toHaveBeenCalledWith('check_backend_health')
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
    vi.mocked(invoke).mockImplementation((cmd: string) => {
      if (cmd === 'check_backend_health') {
        return Promise.resolve(false)
      }
      return Promise.reject(new Error(`unexpected: ${cmd}`))
    })
    await expect(
      waitForBackendHealth('http://127.0.0.1:1', 2, 1),
    ).rejects.toThrow('Backend health check timed out')
  })
})
