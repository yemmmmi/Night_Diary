import type { MemoryCard } from '@/shared/api/card'

export interface MoodTrendPoint {
  date: string
  avgMood: number
  cardCount: number
  emotions: string[]
}

export const MOOD_TREND_DEFAULT_DAYS = 30

export function moodLevelLabel(avgMood: number): string {
  if (avgMood >= 0.66) return '偏高'
  if (avgMood >= 0.4) return '中等'
  return '偏低'
}

/** Build daily mood trend points from memory cards within the last N days. */
export function buildMoodTrendPoints(
  cards: MemoryCard[],
  days: number = MOOD_TREND_DEFAULT_DAYS,
): MoodTrendPoint[] {
  const cutoff = new Date()
  cutoff.setHours(0, 0, 0, 0)
  cutoff.setDate(cutoff.getDate() - (days - 1))
  const cutoffIso = cutoff.toISOString().slice(0, 10)

  const byDate = new Map<string, { scores: number[]; emotions: string[] }>()

  for (const card of cards) {
    const date = card.created_at.slice(0, 10)
    if (date < cutoffIso) continue

    const bucket = byDate.get(date) ?? { scores: [], emotions: [] }
    if (typeof card.mood_score === 'number') {
      bucket.scores.push(card.mood_score)
    }
    const emos =
      card.emotions?.length > 0 ? card.emotions : card.emotion ? [card.emotion] : []
    bucket.emotions.push(...emos.filter(Boolean))
    byDate.set(date, bucket)
  }

  return Array.from(byDate.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, { scores, emotions }]) => ({
      date,
      avgMood:
        scores.length > 0 ? scores.reduce((sum, score) => sum + score, 0) / scores.length : 0.5,
      cardCount: scores.length,
      emotions: [...new Set(emotions)],
    }))
}
