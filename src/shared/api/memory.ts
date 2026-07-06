import { getHttpClient } from '@/shared/api/http'

export interface EpisodicEntry {
  entry_id: string
  event_summary: string
  emotion: string
  reply_insight: string
  importance: number
  timestamp: number
  diary_ids: string[]
  source: string
  tags: string[]
  mood_score: number
  emotions: string[]
  event_date: string | null
}

export interface EpisodicEntryUpdate {
  event_summary?: string
  emotion?: string
  reply_insight?: string
  importance?: number
}

export interface EmotionBaseline {
  average_sentiment: number
  volatility: number
  dominant_emotion: string
}

export interface ImportantPerson {
  name: string
  relation: string
  sentiment: number
}

export interface UserProfile {
  personality_tags: string[]
  emotion_baseline: EmotionBaseline
  important_people: ImportantPerson[]
  recurring_topics: string[]
  preferred_response_style: string
}

export interface MemoryOverview {
  episodic_total: number
  episodic_from_cards: number
  episodic_from_diaries: number
  card_total: number
  profile_built: boolean
}

export async function listEpisodic(): Promise<EpisodicEntry[]> {
  const client = await getHttpClient()
  const { data } = await client.get<EpisodicEntry[]>('/api/v1/memory/episodic')
  return data
}

export async function updateEpisodic(
  entryId: string,
  patch: EpisodicEntryUpdate,
): Promise<EpisodicEntry> {
  const client = await getHttpClient()
  const { data } = await client.patch<EpisodicEntry>(
    `/api/v1/memory/episodic/${entryId}`,
    patch,
  )
  return data
}

export async function deleteEpisodic(entryId: string): Promise<void> {
  const client = await getHttpClient()
  await client.delete(`/api/v1/memory/episodic/${entryId}`)
}

export async function getProfile(): Promise<UserProfile | null> {
  const client = await getHttpClient()
  const { data } = await client.get<UserProfile | null>('/api/v1/memory/profile')
  return data
}

export async function getOverview(): Promise<MemoryOverview> {
  const client = await getHttpClient()
  const { data } = await client.get<MemoryOverview>('/api/v1/memory/overview')
  return data
}
