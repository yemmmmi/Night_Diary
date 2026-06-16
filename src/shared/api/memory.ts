import { getHttpClient } from '@/shared/api/http'

export interface EpisodicEntry {
  entry_id: string
  event: string
  emotion: string
  ai_suggestion: string
  user_feedback: string
  importance: number
  timestamp: number
  diary_ids: string[]
  source: 'card' | 'diary'
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
