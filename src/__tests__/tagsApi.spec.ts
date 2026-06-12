import axios from 'axios'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { mockAxiosClient } from '@/__tests__/helpers/mockAxiosClient'
import { createTag, deleteTag, listTags, seedMoodTags } from '@/shared/api/tags'
import { resetHttpClient } from '@/shared/api/http'

vi.mock('axios', () => {
  const create = vi.fn()
  return { default: { create } }
})

vi.mock('@/shared/composables/useBackend', () => ({
  resolveBackendBaseUrl: vi.fn(async () => 'http://127.0.0.1:8000'),
  waitForCoreReady: vi.fn(async () => undefined),
}))

describe('tags API', () => {
  const get = vi.fn()
  const post = vi.fn()
  const del = vi.fn()

  afterEach(() => {
    vi.clearAllMocks()
    resetHttpClient()
  })

  it('lists tags from /api/v1/tags', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ get, post, delete: del }) as never)
    get.mockResolvedValue({
      data: [{ id: 1, name: '工作', color: '#112233', usage_count: 2, created_at: '2026-01-01T00:00:00' }],
    })

    const tags = await listTags()
    expect(get).toHaveBeenCalledWith('/api/v1/tags')
    expect(tags[0].name).toBe('工作')
  })

  it('creates a tag', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ get, post, delete: del }) as never)
    post.mockResolvedValue({
      data: { id: 2, name: '生活', color: '#6B7280', usage_count: 0, created_at: '2026-01-01T00:00:00' },
    })

    const created = await createTag({ name: '生活' })
    expect(post).toHaveBeenCalledWith('/api/v1/tags', { name: '生活' })
    expect(created.id).toBe(2)
  })

  it('deletes a tag', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ get, post, delete: del }) as never)
    del.mockResolvedValue({})

    await deleteTag(3)
    expect(del).toHaveBeenCalledWith('/api/v1/tags/3')
  })

  it('seeds mood tags', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ get, post, delete: del }) as never)
    post.mockResolvedValue({
      data: [{ id: 1, name: '开心', color: '#10B981' }],
    })

    const tags = await seedMoodTags()
    expect(post).toHaveBeenCalledWith('/api/v1/tags/seed-mood')
    expect(tags[0].name).toBe('开心')
  })
})
