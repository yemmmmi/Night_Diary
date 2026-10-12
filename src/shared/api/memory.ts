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

/** User-authored 「关于我」 — complements the system-inferred long-term profile. */
export interface UserAbout {
  content: string
  updated_at: number
  max_chars: number
}

/** A selectable 回信人格 preset (E1) — tone + length, orthogonal to the mode. */
export interface PersonalityPreset {
  key: string
  label: string
  min_chars: number
  max_chars: number
}

/** The user's chosen 回信人格 preset plus the full option list. */
export interface Personality {
  key: string
  label: string
  presets: PersonalityPreset[]
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

export async function getAbout(): Promise<UserAbout> {
  const client = await getHttpClient()
  const { data } = await client.get<UserAbout>('/api/v1/memory/about')
  return data
}

export async function updateAbout(content: string): Promise<UserAbout> {
  const client = await getHttpClient()
  const { data } = await client.put<UserAbout>('/api/v1/memory/about', { content })
  return data
}

export async function getPersonality(): Promise<Personality> {
  const client = await getHttpClient()
  const { data } = await client.get<Personality>('/api/v1/memory/personality')
  return data
}

export async function updatePersonality(key: string): Promise<Personality> {
  const client = await getHttpClient()
  const { data } = await client.put<Personality>('/api/v1/memory/personality', { key })
  return data
}
