import { describe, expect, it, vi, beforeEach } from 'vitest'

import {
  resetCoreReady,
  resolveBackendBaseUrl,
  waitForBackendHealth,
  waitForCoreReady,
} from '../useBackend'

describe('useBackend helpers', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.unstubAllGlobals()
    resetCoreReady()
  })

  it('resolveBackendBaseUrl returns default dev URL when env not set', async () => {
    await expect(resolveBackendBaseUrl()).resolves.toBe('http://127.0.0.1:8000')
  })

  it('waitForBackendHealth succeeds when fetch returns ok', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, status: 200 }),
    )
    await expect(waitForBackendHealth('http://127.0.0.1:8000')).resolves.toBeUndefined()
    expect(fetch).toHaveBeenCalledWith('http://127.0.0.1:8000/health')
  })

  it('waitForBackendHealth retries on failure then succeeds', async () => {
    let callCount = 0
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(() => {
        callCount++
        if (callCount < 3) {
          return Promise.resolve({ ok: false, status: 503 })
        }
        return Promise.resolve({ ok: true, status: 200 })
      }),
    )
    await expect(
      waitForBackendHealth('http://127.0.0.1:8000', 5, 10),
    ).resolves.toBeUndefined()
    expect(fetch).toHaveBeenCalledTimes(3)
  })

  it('waitForBackendHealth throws after max attempts', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 503 }),
    )
    await expect(
      waitForBackendHealth('http://127.0.0.1:1', 2, 5),
    ).rejects.toThrow('Backend health check timed out')
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('waitForBackendHealth handles fetch errors', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new Error('Network error')),
    )
    await expect(
      waitForBackendHealth('http://127.0.0.1:1', 2, 5),
    ).rejects.toThrow('Backend health check timed out')
  })

  it('waitForCoreReady resolves when /ready returns ok', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, status: 200 }),
    )
    await expect(waitForCoreReady('http://127.0.0.1:8000', 1000)).resolves.toBeUndefined()
    expect(fetch).toHaveBeenCalledWith('http://127.0.0.1:8000/ready')
  })

  it('waitForCoreReady caches result (idempotent)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, status: 200 }),
    )
    await waitForCoreReady('http://127.0.0.1:8000', 1000)
    const firstCallCount = vi.mocked(fetch).mock.calls.length
    await waitForCoreReady('http://127.0.0.1:8000', 1000)
    // Should not fetch again since core is already ready
    expect(vi.mocked(fetch).mock.calls.length).toBe(firstCallCount)
  })
})
