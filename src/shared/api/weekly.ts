import { getHttpClient } from '@/shared/api/http'

export interface WeeklyReport {
  id: number
  period_start: string
  period_end: string
  content: string
  diary_count: number
  card_count: number
  avg_mood: number | null
  token_cost: number | null
  execution_tier: string | null
  created_at: string
}

export async function generateWeekly(): Promise<WeeklyReport> {
  const client = await getHttpClient()
  const { data } = await client.post<WeeklyReport>('/api/v1/weekly')
  return data
}

export async function regenerateWeekly(): Promise<WeeklyReport> {
  const client = await getHttpClient()
  const { data } = await client.post<WeeklyReport>('/api/v1/weekly/regenerate')
  return data
}

export async function listWeekly(params: { skip?: number; limit?: number } = {}): Promise<WeeklyReport[]> {
  const client = await getHttpClient()
  const { data } = await client.get<WeeklyReport[]>('/api/v1/weekly', { params })
  return data
}

export async function getLatestWeekly(): Promise<WeeklyReport> {
  const client = await getHttpClient()
  const { data } = await client.get<WeeklyReport>('/api/v1/weekly/latest')
  return data
}

export async function deleteWeekly(reportId: number): Promise<void> {
  const client = await getHttpClient()
  await client.delete(`/api/v1/weekly/${reportId}`)
}
