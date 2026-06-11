import { getHttpClient } from '@/shared/api/http'

export type FeedbackType = 'positive' | 'negative'

export interface FeedbackCreatePayload {
  feedback_type: FeedbackType
  reason?: string | null
  response_style?: string
}

export interface FeedbackRecord {
  id: number
  analysis_id: number
  diary_id: number
  feedback_type: string
  response_style: string
  reason: string | null
  created_at: string
}

export async function submitFeedback(
  analysisId: number,
  payload: FeedbackCreatePayload,
): Promise<FeedbackRecord> {
  const client = await getHttpClient()
  const { data } = await client.post<FeedbackRecord>(`/api/v1/feedback/${analysisId}`, payload)
  return data
}
