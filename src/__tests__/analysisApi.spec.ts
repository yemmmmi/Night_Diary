import axios from 'axios'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { mockAxiosClient } from '@/__tests__/helpers/mockAxiosClient'
import { getAnalysis, triggerAnalysis } from '@/shared/api/analysis'
import { resetHttpClient } from '@/shared/api/http'

vi.mock('axios', () => {
  const create = vi.fn()
  return { default: { create } }
})

vi.mock('@/shared/composables/useBackend', () => ({
  resolveBackendBaseUrl: vi.fn(async () => 'http://127.0.0.1:8000'),
  waitForCoreReady: vi.fn(async () => undefined),
}))

describe('analysis API', () => {
  const get = vi.fn()
  const post = vi.fn()

  afterEach(() => {
    vi.clearAllMocks()
    resetHttpClient()
  })

  it('triggers analysis for a diary entry', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ get, post }) as never)
    post.mockResolvedValue({
      data: {
        id: 10,
        diary_id: 3,
        created_at: '2026-06-08T12:00:00',
        token_cost: 120,
        cache_hit_tokens: 40,
        cache_miss_tokens: 50,
        output_tokens: 30,
        agent_mode: 'multi_agent',
        execution_tier: 'medium',
        activated_agents: 'empathy,insight',
        ai_ans: '谢谢你愿意分享这些。',
      },
    })

    const result = await triggerAnalysis(3)
    expect(post).toHaveBeenCalledWith('/api/v1/analysis/3', {})
    expect(result.ai_ans).toBe('谢谢你愿意分享这些。')
  })

  it('fetches analysis by diary id', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ get, post }) as never)
    get.mockResolvedValue({
      data: {
        id: 10,
        diary_id: 3,
        created_at: '2026-06-08T12:00:00',
        token_cost: 120,
        cache_hit_tokens: 40,
        cache_miss_tokens: 50,
        output_tokens: 30,
        agent_mode: 'multi_agent',
        execution_tier: 'medium',
        activated_agents: 'empathy,insight',
        ai_ans: '已有回信',
      },
    })

    const result = await getAnalysis(3)
    expect(get).toHaveBeenCalledWith('/api/v1/analysis/3')
    expect(result.diary_id).toBe(3)
  })
})
