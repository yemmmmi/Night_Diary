import type { DiaryEntry } from '@/shared/api/diary'
import type { MemoryCard } from '@/shared/api/card'
import { diaryStatus } from '@/shared/utils/diaryFormat'

export type KanbanItem =
  | { kind: 'diary'; entry: DiaryEntry; linkedCard: MemoryCard | null }
  | { kind: 'card'; card: MemoryCard }

export const KANBAN_VISIBLE_PER_DAY = 2

function itemTimestamp(item: KanbanItem): string {
  return item.kind === 'diary' ? (item.entry.created_at ?? '') : item.card.created_at
}

function itemPriority(item: KanbanItem): number {
  if (item.kind === 'diary') {
    if (diaryStatus(item.entry) === 'reply') return 0
    return 1
  }
  return 2
}

/** Sort: reply diaries first, then other diaries, then cards; newest within tier. */
export function sortKanbanItems(items: KanbanItem[]): KanbanItem[] {
  return [...items].sort((a, b) => {
    const pa = itemPriority(a)
    const pb = itemPriority(b)
    if (pa !== pb) return pa - pb
    return itemTimestamp(b).localeCompare(itemTimestamp(a))
  })
}

export function splitKanbanItems(items: KanbanItem[], maxVisible = KANBAN_VISIBLE_PER_DAY) {
  const sorted = sortKanbanItems(items)
  return {
    visible: sorted.slice(0, maxVisible),
    overflow: sorted.slice(maxVisible),
    overflowCount: Math.max(0, sorted.length - maxVisible),
  }
}
