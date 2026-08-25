import { getHttpClient } from '@/shared/api/http'

export interface DiaryEntry {
  id: number
  content: string | null
  date: string | null
  weather: string | null
  reply: string | null
  created_at: string
  updated_at: string
}

export interface DiaryCreatePayload {
  content: string
  date?: string | null
  weather?: string | null
}

export interface DiaryUpdatePayload {
  content?: string
  weather?: string | null
}

export interface ListDiaryParams {
  skip?: number
  limit?: number
  date_from?: string
  date_to?: string
}

export async function listDiaryEntries(params: ListDiaryParams = {}): Promise<DiaryEntry[]> {
  const client = await getHttpClient()
  const { data } = await client.get<DiaryEntry[]>('/api/v1/diary/entries', { params })
  return data
}

export async function getDiaryEntry(diaryId: number): Promise<DiaryEntry> {
  const client = await getHttpClient()
  const { data } = await client.get<DiaryEntry>(`/api/v1/diary/entries/${diaryId}`)
  return data
}

export async function createDiaryEntry(payload: DiaryCreatePayload): Promise<DiaryEntry> {
  const client = await getHttpClient()
  const { data } = await client.post<DiaryEntry>('/api/v1/diary/entries', payload)
  return data
}

export async function updateDiaryEntry(
  diaryId: number,
  payload: DiaryUpdatePayload,
): Promise<DiaryEntry> {
  const client = await getHttpClient()
  const { data } = await client.put<DiaryEntry>(`/api/v1/diary/entries/${diaryId}`, payload)
  return data
}

export async function deleteDiaryEntry(diaryId: number): Promise<void> {
  const client = await getHttpClient()
  await client.delete(`/api/v1/diary/entries/${diaryId}`)
}
