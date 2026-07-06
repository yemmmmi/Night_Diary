import { describe, expect, it } from 'vitest'

import type { DiaryEntry } from '@/shared/api/diary'
import type { MemoryCard } from '@/shared/api/card'
import {
  KANBAN_VISIBLE_PER_DAY,
  sortKanbanItems,
  splitKanbanItems,
  type KanbanItem,
} from '@/shared/utils/kanbanSort'

function diary(id: number, partial: Partial<DiaryEntry> = {}): KanbanItem {
  return {
    kind: 'diary',
    linkedCard: null,
    entry: {
      id,
      content: partial.content ?? '这是一段足够长的日记正文内容',
      date: partial.date ?? '2026-06-10',
      weather: null,
      reply: partial.reply ?? null,
      created_at: partial.created_at ?? `2026-06-10T10:0${id}:00`,
      updated_at: partial.updated_at ?? `2026-06-10T10:0${id}:00`,
    },
  }
}

function card(cardId: string, createdAt: string): KanbanItem {
  return {
    kind: 'card',
    card: {
      card_id: cardId,
      emotion: '平静',
      emotions: ['平静'],
      event_summary: null,
      mood_score: 0.5,
      importance: 0.5,
      card_type: 'quick',
      tags: [],
      diary_id: null,
      created_at: createdAt,
      updated_at: createdAt,
    } as MemoryCard,
  }
}

describe('kanbanSort', () => {
  it('prioritizes reply diaries, then other diaries, then cards', () => {
    const items: KanbanItem[] = [
      card('c1', '2026-06-10T12:00:00'),
      diary(1, { created_at: '2026-06-10T11:00:00' }),
      diary(2, { reply: '回信', created_at: '2026-06-10T09:00:00' }),
    ]

    const sorted = sortKanbanItems(items)

    expect(sorted.map((item) => (item.kind === 'diary' ? item.entry.id : item.card.card_id))).toEqual([
      2,
      1,
      'c1',
    ])
  })

  it('splits visible items and overflow count', () => {
    const items: KanbanItem[] = [
      diary(1),
      diary(2),
      diary(3),
      card('c1', '2026-06-10T08:00:00'),
    ]

    const { visible, overflowCount } = splitKanbanItems(items)

    expect(visible).toHaveLength(KANBAN_VISIBLE_PER_DAY)
    expect(overflowCount).toBe(2)
  })
})
