import { getHttpClient } from '@/shared/api/http'

export interface TagBrief {
  id: number
  name: string
  color: string
}

export interface DiaryEntry {
  id: number
  content: string | null
  date: string | null
  weather: string | null
  ai_ans: string | null
  created_at: string
  updated_at: string
  tags: TagBrief[]
}

export interface DiaryCreatePayload {
  content: string
  weather?: string | null
  tag_ids?: number[]
}

export interface DiaryUpdatePayload {
  content?: string
  weather?: string | null
  tag_ids?: number[]
}

export interface ListDiaryParams {
  skip?: number
  limit?: number
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
