import axios from 'axios'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { mockAxiosClient } from '@/__tests__/helpers/mockAxiosClient'
import {
  createSchedule,
  deleteSchedule,
  listKinds,
  listRuns,
  listSchedules,
  triggerSchedule,
  updateSchedule,
} from '@/shared/api/schedule'
import { resetHttpClient } from '@/shared/api/http'

vi.mock('axios', () => {
  const create = vi.fn()
  return { default: { create } }
})

vi.mock('@/shared/composables/useBackend', () => ({
  resolveBackendBaseUrl: vi.fn(async () => 'http://127.0.0.1:8000'),
  waitForCoreReady: vi.fn(async () => undefined),
}))

const sampleTask = {
  id: 't1',
  kind: 'daily_review',
  kind_label: '每日回顾',
  mode: 'script',
  mode_label: '纯数据（零 LLM）',
  sink: 'inbox',
  cron_expr: '0 22 * * *',
  payload: {},
  enabled: true,
  next_run_at: '2026-10-12T22:00:00',
  last_run_at: null,
  last_status: null,
  created_at: '2026-10-11T10:00:00',
}

const sampleRun = {
  id: 3,
  task_id: 't1',
  kind: 'daily_review',
  status: 'done',
  summary: '今天有 2 条记录。',
  error: null,
  started_at: '2026-10-11T22:00:00',
  finished_at: '2026-10-11T22:00:05',
}

describe('schedule API', () => {
  const get = vi.fn()
  const post = vi.fn()
  const patch = vi.fn()
  const del = vi.fn()

  afterEach(() => {
    vi.clearAllMocks()
    resetHttpClient()
  })

  it('lists task kinds', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ get }) as never)
    get.mockResolvedValue({ data: [{ kind: 'daily_review', label: '每日回顾' }] })

    const result = await listKinds()
    expect(get).toHaveBeenCalledWith('/api/v1/schedules/kinds')
    expect(result[0].kind).toBe('daily_review')
  })

  it('lists scheduled tasks', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ get }) as never)
    get.mockResolvedValue({ data: [sampleTask] })

    const result = await listSchedules()
    expect(get).toHaveBeenCalledWith('/api/v1/schedules')
    expect(result[0].kind_label).toBe('每日回顾')
  })

  it('creates a scheduled task', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ post }) as never)
    post.mockResolvedValue({ data: sampleTask })

    const result = await createSchedule({
      kind: 'daily_review',
      cron_expr: '0 22 * * *',
      enabled: true,
    })
    expect(post).toHaveBeenCalledWith('/api/v1/schedules', {
      kind: 'daily_review',
      cron_expr: '0 22 * * *',
      enabled: true,
    })
    expect(result.id).toBe('t1')
  })

  it('updates a scheduled task', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ patch }) as never)
    patch.mockResolvedValue({ data: { ...sampleTask, enabled: false } })

    const result = await updateSchedule('t1', { enabled: false })
    expect(patch).toHaveBeenCalledWith('/api/v1/schedules/t1', { enabled: false })
    expect(result.enabled).toBe(false)
  })

  it('deletes a scheduled task', async () => {
    vi.mocked(axios.create).mockReturnValue(
      mockAxiosClient({ delete: del }) as never,
    )
    del.mockResolvedValue({})

    await deleteSchedule('t1')
    expect(del).toHaveBeenCalledWith('/api/v1/schedules/t1')
  })

  it('triggers a scheduled task', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ post }) as never)
    post.mockResolvedValue({ data: sampleTask })

    const result = await triggerSchedule('t1')
    expect(post).toHaveBeenCalledWith('/api/v1/schedules/t1/trigger')
    expect(result.id).toBe('t1')
  })

  it('lists execution receipts with a limit', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ get }) as never)
    get.mockResolvedValue({ data: [sampleRun] })

    const result = await listRuns('t1', 5)
    expect(get).toHaveBeenCalledWith('/api/v1/schedules/t1/runs', { params: { limit: 5 } })
    expect(result[0].status).toBe('done')
  })
})