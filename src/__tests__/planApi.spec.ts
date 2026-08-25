import axios from 'axios'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { mockAxiosClient } from '@/__tests__/helpers/mockAxiosClient'
import { listTasks } from '@/shared/api/plan'
import { resetHttpClient } from '@/shared/api/http'

vi.mock('axios', () => {
  const create = vi.fn()
  return { default: { create } }
})

vi.mock('@/shared/composables/useBackend', () => ({
  resolveBackendBaseUrl: vi.fn(async () => 'http://127.0.0.1:8000'),
  waitForCoreReady: vi.fn(async () => undefined),
}))

describe('plan API', () => {
  const get = vi.fn()

  afterEach(() => {
    vi.clearAllMocks()
    resetHttpClient()
  })

  it('lists tasks with due-date range', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ get }) as never)
    get.mockResolvedValue({ data: [] })

    await listTasks({ date_from: '2026-08-24', date_to: '2026-08-30' })
    expect(get).toHaveBeenCalledWith('/api/v1/tasks', {
      params: { date_from: '2026-08-24', date_to: '2026-08-30' },
    })
  })
})
