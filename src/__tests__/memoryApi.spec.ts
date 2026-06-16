import axios from 'axios'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { mockAxiosClient } from '@/__tests__/helpers/mockAxiosClient'
import { getOverview, getProfile, listEpisodic } from '@/shared/api/memory'
import { resetHttpClient } from '@/shared/api/http'

vi.mock('axios', () => {
  const create = vi.fn()
  return { default: { create } }
})

vi.mock('@/shared/composables/useBackend', () => ({
  resolveBackendBaseUrl: vi.fn(async () => 'http://127.0.0.1:8000'),
  waitForCoreReady: vi.fn(async () => undefined),
}))

const sampleEpisodic = {
  entry_id: 'a1',
  event: '搬家，既兴奋又疲惫',
  emotion: '兴奋',
  ai_suggestion: '',
  user_feedback: 'none',
  importance: 0.7,
  timestamp: 1781510000,
  diary_ids: [],
  source: 'card' as const,
}

const sampleProfile = {
  personality_tags: ['内省'],
  emotion_baseline: { average_sentiment: 0.4, volatility: 0.2, dominant_emotion: '平静' },
  important_people: [{ name: '妈妈', relation: '家人', sentiment: 0.8 }],
  recurring_topics: ['工作'],
  preferred_response_style: 'empathetic',
}

const sampleOverview = {
  episodic_total: 2,
  episodic_from_cards: 1,
  episodic_from_diaries: 1,
  card_total: 1,
  profile_built: true,
}

describe('memory API', () => {
  const get = vi.fn()

  afterEach(() => {
    vi.clearAllMocks()
    resetHttpClient()
  })

  it('lists episodic memory entries', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ get }) as never)
    get.mockResolvedValue({ data: [sampleEpisodic] })

    const result = await listEpisodic()
    expect(get).toHaveBeenCalledWith('/api/v1/memory/episodic')
    expect(result).toHaveLength(1)
    expect(result[0].source).toBe('card')
  })

  it('fetches the long-term profile', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ get }) as never)
    get.mockResolvedValue({ data: sampleProfile })

    const result = await getProfile()
    expect(get).toHaveBeenCalledWith('/api/v1/memory/profile')
    expect(result?.personality_tags).toContain('内省')
  })

  it('returns null when no profile exists', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ get }) as never)
    get.mockResolvedValue({ data: null })

    const result = await getProfile()
    expect(result).toBeNull()
  })

  it('fetches the memory overview', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ get }) as never)
    get.mockResolvedValue({ data: sampleOverview })

    const result = await getOverview()
    expect(get).toHaveBeenCalledWith('/api/v1/memory/overview')
    expect(result.episodic_from_cards).toBe(1)
  })
})
