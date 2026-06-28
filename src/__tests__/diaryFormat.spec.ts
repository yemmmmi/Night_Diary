import { describe, expect, it } from 'vitest'

import type { MemoryCard } from '@/shared/api/card'
import type { DiaryEntry } from '@/shared/api/diary'
import {
  computeWritingStreak,
  diaryEntrySummary,
  diaryStatus,
  diaryStatusLabel,
  diarySummary,
  groupEntriesForWeek,
  startOfWeekMonday,
  toIsoDate,
} from '@/shared/utils/diaryFormat'

function entry(partial: Partial<DiaryEntry> & Pick<DiaryEntry, 'id'>): DiaryEntry {
  return {
    content: partial.content ?? '内容',
    date: partial.date ?? null,
    weather: null,
    ai_ans: partial.ai_ans ?? null,
    created_at: partial.created_at ?? '2026-06-08T10:00:00',
    updated_at: partial.updated_at ?? '2026-06-08T10:00:00',
    ...partial,
  }
}

describe('diaryFormat', () => {
  it('summarizes first line', () => {
    expect(diarySummary('第一行\n第二行')).toBe('第一行')
  })

  it('returns fallback for empty content', () => {
    expect(diarySummary('')).toBe('空白日记')
    expect(diarySummary(null)).toBe('空白日记')
  })

  it('returns custom fallback for empty content', () => {
    expect(diarySummary('', 28, '给夜记1.0收尾修bug')).toBe('给夜记1.0收尾修bug')
    expect(diarySummary(null, 28, '卡片描述')).toBe('卡片描述')
  })

  it('uses linked card event when diary content is empty', () => {
    const cards: MemoryCard[] = [
      {
        card_id: 'c1',
        emotion: '疲惫',
        emotions: ['疲惫'],
        event_summary: '给夜记1.0收尾修bug，累死了',
        mood_score: 0.3,
        tags: [],
        importance: 0.5,
        card_type: 'standard',
        diary_id: 7,
        created_at: '2026-06-27T10:00:00',
        updated_at: '2026-06-27T10:00:00',
      },
    ]
    const diary = entry({ id: 7, content: '', date: '2026-06-27' })
    expect(diaryEntrySummary(diary, cards)).toBe('给夜记1.0收尾修bug，累死了')
  })

  it('returns empty label for draft status', () => {
    expect(diaryStatusLabel('draft')).toBe('')
    expect(diaryStatusLabel('reply')).toBe('已有回信')
    expect(diaryStatusLabel('pending')).toBe('待分析')
  })

  it('derives diary status', () => {
    expect(diaryStatus(entry({ id: 1, ai_ans: '回信' }))).toBe('reply')
    expect(diaryStatus(entry({ id: 2, content: '短' }))).toBe('draft')
    expect(diaryStatus(entry({ id: 3, content: '这是一段足够长的日记内容' }))).toBe('pending')
  })

  it('groups entries into week columns and inbox', () => {
    const weekStart = startOfWeekMonday(new Date('2026-06-08T12:00:00'))
    const weekEnd = new Date(weekStart)
    weekEnd.setDate(weekEnd.getDate() + 6)

    const inWeek = entry({ id: 1, date: toIsoDate(weekStart) })
    const outWeek = entry({ id: 2, date: '2020-01-01' })

    const grouped = groupEntriesForWeek([inWeek, outWeek], weekStart, weekEnd)
    expect(grouped.dayColumns.get(toIsoDate(weekStart))).toHaveLength(1)
    expect(grouped.inbox).toHaveLength(1)
  })

  it('computes writing streak from consecutive dates', () => {
    const today = toIsoDate(new Date())
    const yesterday = toIsoDate(new Date(Date.now() - 86_400_000))
    const streak = computeWritingStreak([
      entry({ id: 1, date: today }),
      entry({ id: 2, date: yesterday }),
    ])
    expect(streak).toBeGreaterThanOrEqual(2)
  })
})
