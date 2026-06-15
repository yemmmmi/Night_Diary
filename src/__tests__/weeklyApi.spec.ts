import axios from 'axios'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { mockAxiosClient } from '@/__tests__/helpers/mockAxiosClient'
import { deleteWeekly, generateWeekly, getLatestWeekly, listWeekly } from '@/shared/api/weekly'
import { resetHttpClient } from '@/shared/api/http'

vi.mock('axios', () => {
  const create = vi.fn()
  return { default: { create } }
})

vi.mock('@/shared/composables/useBackend', () => ({
  resolveBackendBaseUrl: vi.fn(async () => 'http://127.0.0.1:8000'),
  waitForCoreReady: vi.fn(async () => undefined),
}))

const sampleReport = {
  id: 1,
  period_start: '2026-06-08',
  period_end: '2026-06-14',
  content: '这一周你经历了许多。',
  diary_count: 3,
  card_count: 5,
  avg_mood: 0.62,
  token_cost: 800,
  execution_tier: 'medium',
  created_at: '2026-06-14T20:00:00',
}

describe('weekly API', () => {
  const get = vi.fn()
  const post = vi.fn()
  const del = vi.fn()

  afterEach(() => {
    vi.clearAllMocks()
    resetHttpClient()
  })

  it('generates the current weekly report', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ get, post, delete: del }) as never)
    post.mockResolvedValue({ data: sampleReport })

    const result = await generateWeekly()
    expect(post).toHaveBeenCalledWith('/api/v1/weekly')
    expect(result.diary_count).toBe(3)
    expect(result.content).toContain('这一周')
  })

  it('lists weekly reports', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ get, post, delete: del }) as never)
    get.mockResolvedValue({ data: [sampleReport] })

    const result = await listWeekly({ limit: 52 })
    expect(get).toHaveBeenCalledWith('/api/v1/weekly', { params: { limit: 52 } })
    expect(result).toHaveLength(1)
  })

  it('fetches the latest weekly report', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ get, post, delete: del }) as never)
    get.mockResolvedValue({ data: sampleReport })

    const result = await getLatestWeekly()
    expect(get).toHaveBeenCalledWith('/api/v1/weekly/latest')
    expect(result.id).toBe(1)
  })

  it('deletes a weekly report', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ get, post, delete: del }) as never)
    del.mockResolvedValue({ data: undefined })

    await deleteWeekly(1)
    expect(del).toHaveBeenCalledWith('/api/v1/weekly/1')
  })
})
