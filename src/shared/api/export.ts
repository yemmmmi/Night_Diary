import { getHttpClient } from '@/shared/api/http'

export interface ExportSummary {
  diaries: number
  tags: number
  analyses: number
  memory_cards: number
  episodic_memories: number
  long_term_profile: number
}

/** Export all user data as a JSON blob. */
export async function exportAll(): Promise<Record<string, unknown>> {
  const client = await getHttpClient()
  const { data } = await client.get('/export/all')
  return data
}

/** Import user data from a JSON blob, replacing all existing data. */
export async function importJson(data: Record<string, unknown>): Promise<ExportSummary> {
  const client = await getHttpClient()
  const res = await client.post('/import/json', { data })
  return res.data.imported as ExportSummary
}
