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
  ai_ans: string | null
  model_name: string | null
  status_detail: string | null
}

export async function triggerAnalysis(diaryId: number): Promise<AnalysisRecord> {
  const client = await getHttpClient()
  const { data } = await client.post<AnalysisRecord>(`/api/v1/analysis/${diaryId}`)
  return data
}

export async function regenerateAnalysis(diaryId: number): Promise<AnalysisRecord> {
  const client = await getHttpClient()
  const { data } = await client.post<AnalysisRecord>(`/api/v1/analysis/${diaryId}/regenerate`)
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
