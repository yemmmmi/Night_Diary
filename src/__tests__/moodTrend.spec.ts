import { describe, expect, it } from 'vitest'

import type { MemoryCard } from '@/shared/api/card'
import { buildMoodTrendPoints, moodLevelLabel } from '@/shared/utils/moodTrend'

function card(partial: Partial<MemoryCard> & Pick<MemoryCard, 'card_id' | 'created_at'>): MemoryCard {
  return {
    emotion: '平静',
    emotions: ['平静'],
    event_summary: null,
    mood_score: 0.5,
    card_type: 'quick',
    tags: [],
    diary_id: null,
    updated_at: partial.created_at,
    ...partial,
  } as MemoryCard
}

describe('moodTrend', () => {
  it('groups cards by day with emotions for tooltip', () => {
    const points = buildMoodTrendPoints(
      [
        card({
          card_id: 'a',
          created_at: '2026-06-16T10:00:00',
          mood_score: 0.8,
          emotions: ['平静', '期待'],
        }),
        card({
          card_id: 'b',
          created_at: '2026-06-23T10:00:00',
          mood_score: 0.3,
          emotion: '疲惫',
          emotions: ['疲惫'],
        }),
      ],
      30,
    )

    expect(points).toHaveLength(2)
    expect(points[0].date).toBe('2026-06-16')
    expect(points[0].emotions).toEqual(['平静', '期待'])
    expect(points[1].avgMood).toBeCloseTo(0.3)
  })

  it('labels mood level', () => {
    expect(moodLevelLabel(0.8)).toBe('偏高')
    expect(moodLevelLabel(0.5)).toBe('中等')
    expect(moodLevelLabel(0.2)).toBe('偏低')
  })
})
