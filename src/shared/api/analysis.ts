import { getHttpClient } from '@/shared/api/http'

export interface AnalysisRecord {
  id: number
  diary_id: number
  created_at: string
  token_cost: number | null
  cache_hit_tokens: number | null
  cache_miss_tokens: number | null
  output_tokens: number | null
  agent_mode: string | null
  execution_tier: string | null
  activated_agents: string | null
  reply: string | null
  model_name: string | null
  status_detail: string | null
  referenced_memory_count?: number
}

export interface AnalysisTriggerPayload {
  replier_preset?: string
  replier_persona?: string
}

export async function triggerAnalysis(
  diaryId: number,
  payload?: AnalysisTriggerPayload,
): Promise<AnalysisRecord> {
  const client = await getHttpClient()
  const { data } = await client.post<AnalysisRecord>(`/api/v1/analysis/${diaryId}`, payload ?? {})
  return data
}

export async function regenerateAnalysis(
  diaryId: number,
  payload?: AnalysisTriggerPayload,
): Promise<AnalysisRecord> {
  const client = await getHttpClient()
  const { data } = await client.post<AnalysisRecord>(
    `/api/v1/analysis/${diaryId}/regenerate`,
    payload ?? {},
  )
  return data
}

export async function deleteAnalysis(diaryId: number): Promise<void> {
  const client = await getHttpClient()
  await client.delete(`/api/v1/analysis/${diaryId}`)
}

export async function getAnalysis(diaryId: number): Promise<AnalysisRecord> {
  const client = await getHttpClient()
  const { data } = await client.get<AnalysisRecord>(`/api/v1/analysis/${diaryId}`)
  return data
}

export interface StreamingTriggerResponse {
  streaming: boolean
  trace_id: string
}

/**
 * Trigger a streaming analysis for the given diary entry.
 *
 * The backend responds with `{ streaming, trace_id }`. When `streaming` is
 * `true`, the SSE event stream can be consumed via the shared trace endpoint
 * (`GET /api/v1/dev/traces/{trace_id}/stream`). When `streaming` is `false`,
 * the caller must fall back to the synchronous `triggerAnalysis` path.
 *
 * An optional replier payload is forwarded so that the streaming trigger
 * honours the same replier preset / persona selection as the sync path.
 */
export async function triggerAnalysisStreaming(
  diaryId: number,
  payload?: AnalysisTriggerPayload,
): Promise<StreamingTriggerResponse> {
  const client = await getHttpClient()
  const { data } = await client.post<StreamingTriggerResponse>(
    `/api/v1/analysis/${diaryId}/stream`,
    payload ?? {},
  )
  return data
}
