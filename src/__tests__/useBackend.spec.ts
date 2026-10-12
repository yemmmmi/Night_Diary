import { afterEach, describe, expect, it } from 'vitest'

import { resolveBackendBaseUrl } from '@/shared/composables/useBackend'

describe('resolveBackendBaseUrl', () => {
  afterEach(() => {
    delete (window as unknown as { __NIGHT_DIARY__?: unknown }).__NIGHT_DIARY__
  })

  it('prefers the runtime-injected backend url', async () => {
    ;(window as unknown as { __NIGHT_DIARY__?: { backendUrl?: string } }).__NIGHT_DIARY__ = {
      backendUrl: 'http://127.0.0.1:9123',
    }
    await expect(resolveBackendBaseUrl()).resolves.toBe('http://127.0.0.1:9123')
  })

  it('falls back to the dev default when nothing is injected', async () => {
    await expect(resolveBackendBaseUrl()).resolves.toBe('http://127.0.0.1:8000')
  })
})