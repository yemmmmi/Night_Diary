import { getHttpClient } from '@/shared/api/http'

export interface AppStats {
  diary_count: number
  analysis_count: number
  total_token_cost: number
  llm_call_count: number
  total_tokens_in: number
  total_tokens_out: number
}

export async function getStats(): Promise<AppStats> {
  const client = await getHttpClient()
  const { data } = await client.get<AppStats>('/api/v1/stats')
  return data
}
