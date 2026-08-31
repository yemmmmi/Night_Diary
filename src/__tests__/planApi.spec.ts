import axios from 'axios'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { mockAxiosClient } from '@/__tests__/helpers/mockAxiosClient'
import { createPlan, listTasks, updateTaskStatus } from '@/shared/api/plan'
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
  const post = vi.fn()
  const patch = vi.fn()

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

  it('createPlan carries recurrence and target fields', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ post }) as never)
    post.mockResolvedValue({ data: {} })

    await createPlan({
      title: '早睡挑战',
      recurrence: 'weekly:2,4',
      target_value: 4,
      target_unit: 'h',
      target_period: 'weekly',
    })
    expect(post).toHaveBeenCalledWith(
      '/api/v1/plans',
      expect.objectContaining({ recurrence: 'weekly:2,4', target_value: 4 }),
    )
  })

  it('updateTaskStatus sends actual_value when completing with a value', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ patch }) as never)
    patch.mockResolvedValue({ data: {} })

    await updateTaskStatus('t1', 'done', 2.5)
    expect(patch).toHaveBeenCalledWith('/api/v1/tasks/t1', {
      status: 'done',
      actual_value: 2.5,
    })
  })

  it('updateTaskStatus omits actual_value when not completing', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ patch }) as never)
    patch.mockResolvedValue({ data: {} })

    await updateTaskStatus('t1', 'pending', 2.5)
    expect(patch).toHaveBeenCalledWith('/api/v1/tasks/t1', { status: 'pending' })
  })
})
