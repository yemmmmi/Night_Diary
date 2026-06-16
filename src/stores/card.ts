import { ref } from 'vue'
import { defineStore } from 'pinia'
import {
  listCards,
  deleteCard,
  createCard,
  expandCardToDiary,
  getCardStats,
} from '@/shared/api/card'
import type { MemoryCard, ListCardsParams, CardStats, CardCreatePayload } from '@/shared/api/card'
import { formatApiError } from '@/shared/utils/apiError'

export const useCardStore = defineStore('card', () => {
  // ── State ─────────────────────────────────────────────────────
  const cards = ref<MemoryCard[]>([])
  const stats = ref<CardStats | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const showCardDrawer = ref(false)

  // ── Actions ───────────────────────────────────────────────────

  async function loadCards(params: ListCardsParams = {}) {
    loading.value = true
    error.value = null
    try {
      cards.value = await listCards(params)
    } catch (err) {
      error.value = formatApiError(err, '加载卡片失败')
    } finally {
      loading.value = false
    }
  }

  async function loadStats() {
    try {
      stats.value = await getCardStats()
    } catch {
      stats.value = null
    }
  }

  async function removeCard(cardId: string) {
    try {
      await deleteCard(cardId)
      cards.value = cards.value.filter(c => c.card_id !== cardId)
    } catch (err) {
      throw new Error(formatApiError(err, '删除卡片失败'))
    }
  }

  async function expandCard(cardId: string) {
    try {
      const result = await expandCardToDiary(cardId)
      // Mark the card as expanded in local state
      const idx = cards.value.findIndex(c => c.card_id === cardId)
      if (idx !== -1) {
        cards.value[idx] = { ...cards.value[idx], diary_id: result.diary_id }
      }
      return result
    } catch (err) {
      throw new Error(formatApiError(err, '展开卡片失败'))
    }
  }

  function openDrawer() {
    showCardDrawer.value = true
  }

  function closeDrawer() {
    showCardDrawer.value = false
  }

  async function createFromChat(payload: CardCreatePayload) {
    error.value = null
    try {
      const card = await createCard(payload)
      cards.value = [card, ...cards.value]
      return card
    } catch (err) {
      error.value = formatApiError(err, '保存卡片失败')
      return null
    }
  }

  return {
    cards,
    stats,
    loading,
    error,
    showCardDrawer,
    loadCards,
    loadStats,
    removeCard,
    expandCard,
    openDrawer,
    closeDrawer,
    createFromChat,
  }
})
