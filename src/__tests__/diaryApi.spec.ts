import axios from 'axios'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { mockAxiosClient } from '@/__tests__/helpers/mockAxiosClient'
import { createDiaryEntry, listDiaryEntries } from '@/shared/api/diary'
import { resetHttpClient } from '@/shared/api/http'

vi.mock('axios', () => {
  const create = vi.fn()
  return { default: { create } }
})

vi.mock('@/shared/composables/useBackend', () => ({
  resolveBackendBaseUrl: vi.fn(async () => 'http://127.0.0.1:8000'),
  waitForCoreReady: vi.fn(async () => undefined),
}))

describe('diary API', () => {
  const get = vi.fn()
  const post = vi.fn()

  afterEach(() => {
    vi.clearAllMocks()
    resetHttpClient()
  })

  it('lists diary entries', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ get, post }) as never)
    get.mockResolvedValue({
      data: [
        {
          id: 1,
          content: '测试日记',
          date: '2026-06-08',
          weather: null,
          ai_ans: null,
          created_at: '2026-06-08T10:00:00',
          updated_at: '2026-06-08T10:00:00',
        },
      ],
    })

    const entries = await listDiaryEntries({ limit: 20 })
    expect(get).toHaveBeenCalledWith('/api/v1/diary/entries', { params: { limit: 20 } })
    expect(entries[0].content).toBe('测试日记')
  })

  it('creates a diary entry', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ get, post }) as never)
    post.mockResolvedValue({
      data: {
        id: 2,
        content: '新建日记',
        date: '2026-06-08',
        weather: null,
        ai_ans: null,
        created_at: '2026-06-08T11:00:00',
        updated_at: '2026-06-08T11:00:00',
      },
    })

    const created = await createDiaryEntry({ content: '新建日记', date: '2025-06-01' })
    expect(post).toHaveBeenCalledWith('/api/v1/diary/entries', {
      content: '新建日记',
      date: '2025-06-01',
    })
    expect(created.id).toBe(2)
  })
})
