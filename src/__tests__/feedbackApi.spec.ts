import axios from 'axios'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { mockAxiosClient } from '@/__tests__/helpers/mockAxiosClient'
import { submitFeedback } from '@/shared/api/feedback'
import { resetHttpClient } from '@/shared/api/http'

vi.mock('axios', () => {
  const create = vi.fn()
  return { default: { create } }
})

vi.mock('@/shared/composables/useBackend', () => ({
  resolveBackendBaseUrl: vi.fn(async () => 'http://127.0.0.1:8000'),
  waitForCoreReady: vi.fn(async () => undefined),
}))

describe('feedback API', () => {
  const post = vi.fn()

  afterEach(() => {
    vi.clearAllMocks()
    resetHttpClient()
  })

  it('submits positive feedback', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ post }) as never)
    post.mockResolvedValue({
      data: {
        id: 1,
        analysis_id: 10,
        diary_id: 3,
        feedback_type: 'positive',
        response_style: 'empathetic',
        reason: null,
        created_at: '2026-06-08T12:05:00',
      },
    })

    const result = await submitFeedback(10, { feedback_type: 'positive' })
    expect(post).toHaveBeenCalledWith('/api/v1/feedback/10', { feedback_type: 'positive' })
    expect(result.feedback_type).toBe('positive')
  })

  it('submits negative feedback with reason', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ post }) as never)
    post.mockResolvedValue({
      data: {
        id: 2,
        analysis_id: 10,
        diary_id: 3,
        feedback_type: 'negative',
        response_style: 'empathetic',
        reason: 'too_long',
        created_at: '2026-06-08T12:06:00',
      },
    })

    const result = await submitFeedback(10, {
      feedback_type: 'negative',
      reason: 'too_long',
    })
    expect(post).toHaveBeenCalledWith('/api/v1/feedback/10', {
      feedback_type: 'negative',
      reason: 'too_long',
    })
    expect(result.reason).toBe('too_long')
  })
})
