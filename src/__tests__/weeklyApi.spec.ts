import axios from 'axios'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { mockAxiosClient } from '@/__tests__/helpers/mockAxiosClient'
import { getMoodTrends } from '@/shared/api/card'
import { generateWeekly, listWeekly } from '@/shared/api/weekly'
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
  plan_executions: [],
  week_tasks: [],
}

const structuredReport = {
  ...sampleReport,
  plan_executions: [
    {
      plan_id: 'p1',
      title: '早睡挑战',
      done: 1,
      total: 2,
      source_refs: [{ type: 'diary', id: 1, date: '2026-08-24', snippet: '最近总是熬夜' }],
    },
  ],
  week_tasks: [
    { task_id: 't1', title: '周末散步', status: 'done', source: 'agent', due_date: null },
  ],
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

  it('passes date range to mood trends', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ get, post, delete: del }) as never)
    get.mockResolvedValue({ data: [] })

    await getMoodTrends({ date_from: '2026-08-24', date_to: '2026-08-30' })
    expect(get).toHaveBeenCalledWith('/api/v1/cards/stats/mood-trends', {
      params: { date_from: '2026-08-24', date_to: '2026-08-30' },
    })
  })

  it('returns structured plan execution fields on reports', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ get, post, delete: del }) as never)
    get.mockResolvedValue({ data: [structuredReport] })

    const result = await listWeekly({ limit: 52 })
    expect(result[0].plan_executions[0].title).toBe('早睡挑战')
    expect(result[0].week_tasks[0].status).toBe('done')
  })
})
