import { describe, expect, it } from 'vitest'

import type { DiaryEntry } from '@/shared/api/diary'
import {
  computeWritingStreak,
  diaryStatus,
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
    tags: [],
    ...partial,
  }
}

describe('diaryFormat', () => {
  it('summarizes first line', () => {
    expect(diarySummary('第一行\n第二行')).toBe('第一行')
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
