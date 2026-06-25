import { cardCopy } from '@/shared/copy/card'
import type { MemoryCard } from '@/shared/api/card'

/** Human-readable label for a memory card's capture mode. */
export function cardTypeLabel(cardType: string): string {
  if (cardType === 'quick') return cardCopy.cardTypeQuick
  if (cardType === 'guided') return cardCopy.cardTypeGuided
  return cardCopy.cardTypeStandard
}

/** Find the memory card expanded into a diary entry, if any. */
export function findCardForDiary(cards: MemoryCard[], diaryId: number): MemoryCard | null {
  return cards.find((c) => c.diary_id === diaryId) ?? null
}
