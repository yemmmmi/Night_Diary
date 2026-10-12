import axios from 'axios'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { mockAxiosClient } from '@/__tests__/helpers/mockAxiosClient'
import {
  createCustomSkill,
  deleteCustomSkill,
  listCustomSkills,
  listCustomSkillVersions,
  setCustomSkillEnabled,
  updateCustomSkill,
} from '@/shared/api/customSkills'
import { resetHttpClient } from '@/shared/api/http'

vi.mock('axios', () => {
  const create = vi.fn()
  return { default: { create } }
})

vi.mock('@/shared/composables/useBackend', () => ({
  resolveBackendBaseUrl: vi.fn(async () => 'http://127.0.0.1:8000'),
  waitForCoreReady: vi.fn(async () => undefined),
}))

const sampleSkill = {
  id: 1,
  name: '跑步复盘',
  description: '更关注配速',
  triggers: ['跑步', '配速'],
  instruction: '先问配速，再给一句鼓励。',
  enabled: true,
  version: 1,
  created_at: 0,
  updated_at: 0,
}

describe('custom-skills API', () => {
  const get = vi.fn()
  const post = vi.fn()
  const patch = vi.fn()
  const del = vi.fn()

  afterEach(() => {
    vi.clearAllMocks()
    resetHttpClient()
  })

  it('lists custom skills', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ get }) as never)
    get.mockResolvedValue({ data: [sampleSkill] })

    const result = await listCustomSkills()
    expect(get).toHaveBeenCalledWith('/api/v1/custom-skills')
    expect(result[0].name).toBe('跑步复盘')
  })

  it('creates a custom skill', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ post }) as never)
    post.mockResolvedValue({ data: sampleSkill })

    const body = {
      name: '跑步复盘',
      description: '更关注配速',
      triggers: ['跑步', '配速'],
      instruction: '先问配速，再给一句鼓励。',
    }
    const result = await createCustomSkill(body)
    expect(post).toHaveBeenCalledWith('/api/v1/custom-skills', body)
    expect(result.id).toBe(1)
  })

  it('updates a custom skill', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ patch }) as never)
    patch.mockResolvedValue({ data: { ...sampleSkill, name: '跑步复盘 v2', version: 2 } })

    const body = {
      name: '跑步复盘 v2',
      description: '',
      triggers: ['跑步'],
      instruction: '先问距离。',
    }
    const result = await updateCustomSkill(1, body)
    expect(patch).toHaveBeenCalledWith('/api/v1/custom-skills/1', body)
    expect(result.version).toBe(2)
  })

  it('toggles a custom skill', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ patch }) as never)
    patch.mockResolvedValue({ data: { ...sampleSkill, enabled: false } })

    const result = await setCustomSkillEnabled(1, false)
    expect(patch).toHaveBeenCalledWith('/api/v1/custom-skills/1/enabled', { enabled: false })
    expect(result.enabled).toBe(false)
  })

  it('deletes a custom skill', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ delete: del }) as never)
    del.mockResolvedValue({})

    await deleteCustomSkill(1)
    expect(del).toHaveBeenCalledWith('/api/v1/custom-skills/1')
  })

  it('lists prior versions', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ get }) as never)
    get.mockResolvedValue({ data: [{ ...sampleSkill, version: 1 }] })

    const result = await listCustomSkillVersions(1)
    expect(get).toHaveBeenCalledWith('/api/v1/custom-skills/1/versions')
    expect(result[0].version).toBe(1)
  })
})