import { getHttpClient } from '@/shared/api/http'

export interface MemoryCard {
  card_id: string
  emotion: string
  emotions: string[]
  event_summary: string | null
  mood_score: number
  tags: string[]
  importance: number
  card_type: string
  diary_id: number | null
  created_at: string
  updated_at: string
}

export interface CardCreatePayload {
  emotion: string
  emotions?: string[]
  event_summary?: string | null
  mood_score?: number
  tags?: string[]
  importance?: number
  card_type?: 'quick' | 'standard' | 'guided'
}

export interface ListCardsParams {
  skip?: number
  limit?: number
  emotion?: string
  card_type?: string
  has_diary?: boolean
}

export interface CardExpandResult {
  card_id: string
  diary_id: number
  message: string
}

export interface CardStats {
  total_cards: number
  expanded_to_diary: number
  not_expanded: number
  average_mood_score: number
  top_emotions: Array<{ emotion: string; count: number }>
}

export async function listCards(params: ListCardsParams = {}): Promise<MemoryCard[]> {
  const client = await getHttpClient()
  const { data } = await client.get<MemoryCard[]>('/api/v1/cards', { params })
  return data
}

export async function createCard(payload: CardCreatePayload): Promise<MemoryCard> {
  const client = await getHttpClient()
  const { data } = await client.post<MemoryCard>('/api/v1/cards', payload)
  return data
}

export async function deleteCard(cardId: string): Promise<void> {
  const client = await getHttpClient()
  await client.delete(`/api/v1/cards/${cardId}`)
}

export async function expandCardToDiary(cardId: string): Promise<CardExpandResult> {
  const client = await getHttpClient()
  const { data } = await client.post<CardExpandResult>(`/api/v1/cards/${cardId}/expand`, {})
  return data
}

export async function getCardStats(): Promise<CardStats> {
  const client = await getHttpClient()
  const { data } = await client.get<CardStats>('/api/v1/cards/stats/summary')
  return data
}

// ── Mood trends ────────────────────────────────────────────────────

export interface MoodTrendPoint {
  date: string
  avg_mood: number
  card_count: number
}

export async function getMoodTrends(days: number = 30): Promise<MoodTrendPoint[]> {
  const client = await getHttpClient()
  const { data } = await client.get<MoodTrendPoint[]>('/api/v1/cards/stats/mood-trends', {
    params: { days },
  })
  return data
}

// ── Guided prompt ──────────────────────────────────────────────────

export interface CardPromptResult {
  questions: string[]
}

export async function generateCardPrompt(): Promise<CardPromptResult> {
  const client = await getHttpClient()
  const { data } = await client.post<CardPromptResult>('/api/v1/cards/prompt', {})
  return data
}

// ── Semantic search ────────────────────────────────────────────────

export interface CardSearchResult extends MemoryCard {
  _distance: number
}

export async function searchCards(
  q: string,
  limit: number = 10,
): Promise<{ query: string; results: CardSearchResult[] }> {
  const client = await getHttpClient()
  const { data } = await client.get<{ query: string; results: CardSearchResult[] }>(
    '/api/v1/cards/search',
    { params: { q, limit } },
  )
  return data
}
