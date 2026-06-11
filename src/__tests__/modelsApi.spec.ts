import axios from 'axios'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { mockAxiosClient } from '@/__tests__/helpers/mockAxiosClient'
import { resetHttpClient } from '@/shared/api/http'
import { createModel, listModels } from '@/shared/api/models'

vi.mock('axios', () => {
  const create = vi.fn()
  return { default: { create } }
})

vi.mock('@/shared/composables/useBackend', () => ({
  resolveBackendBaseUrl: vi.fn(async () => 'http://127.0.0.1:8000'),
  waitForCoreReady: vi.fn(async () => undefined),
}))

describe('models API', () => {
  const get = vi.fn()
  const post = vi.fn()

  afterEach(() => {
    vi.clearAllMocks()
    resetHttpClient()
  })

  it('lists models from /api/v1/models', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ get, post }) as never)
    get.mockResolvedValue({
      data: [
        {
          id: 1,
          model_name: 'deepseek-chat',
          base_url: 'https://api.deepseek.com/v1',
          tier: 'default',
          is_active: true,
          is_default: false,
          has_api_key: true,
        },
      ],
    })

    const models = await listModels()
    expect(get).toHaveBeenCalledWith('/api/v1/models')
    expect(models).toHaveLength(1)
    expect(models[0].model_name).toBe('deepseek-chat')
  })

  it('creates a model via POST', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ get, post }) as never)
    post.mockResolvedValue({
      data: {
        id: 2,
        model_name: 'gpt-4o',
        base_url: 'https://api.openai.com/v1',
        tier: 'heavy',
        is_active: true,
        is_default: false,
        has_api_key: true,
      },
    })

    const created = await createModel({
      model_name: 'gpt-4o',
      api_key: 'sk-test',
      base_url: 'https://api.openai.com/v1',
      tier: 'heavy',
      is_active: true,
    })

    expect(post).toHaveBeenCalledWith('/api/v1/models', {
      model_name: 'gpt-4o',
      api_key: 'sk-test',
      base_url: 'https://api.openai.com/v1',
      tier: 'heavy',
      is_active: true,
    })
    expect(created.tier).toBe('heavy')
  })
})
