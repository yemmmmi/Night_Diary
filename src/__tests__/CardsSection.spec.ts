import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

const push = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}))

const searchCards = vi.fn()

vi.mock('@/shared/api/card', () => ({
  searchCards: (...args: unknown[]) => searchCards(...args),
  listCards: vi.fn(async () => []),
}))

import CardsSection from '@/features/memory/CardsSection.vue'
import { useCardStore } from '@/stores/card'
import type { MemoryCard } from '@/shared/api/card'

const linkedCard: MemoryCard = {
  card_id: 'c1',
  diary_id: 7,
  event_summary: '散步时想通了换工作的事',
  emotions: ['平静'],
  emotion: '平静',
  mood_score: 0.5,
  tags: ['散步'],
  importance: 3,
  card_type: 'event',
  created_at: '2026-08-25T21:00:00',
  updated_at: '2026-08-25T21:00:00',
}

const standaloneCard: MemoryCard = { ...linkedCard, card_id: 'c2', diary_id: null }

function mountSection(cards: MemoryCard[] = []) {
  setActivePinia(createPinia())
  const store = useCardStore()
  store.cards = cards
  store.expandCard = vi.fn(async () => ({ ...standaloneCard, diary_id: 9, message: 'ok' }))
  store.removeCard = vi.fn(async () => {})
  store.loadCards = vi.fn(async () => {})
  return { wrapper: mount(CardsSection), store }
}

describe('CardsSection', () => {
  it('renders cards with summary and time', () => {
    const { wrapper } = mountSection([linkedCard])
    expect(wrapper.text()).toContain('散步时想通了换工作的事')
    expect(wrapper.text()).toContain('平静')
  })

  it('shows empty state when no cards', () => {
    const { wrapper } = mountSection([])
    expect(wrapper.text()).toContain('还没有记忆卡片')
  })

  it('searches and replaces the list with results', async () => {
    searchCards.mockResolvedValue({
      query: '海边',
      results: [{ ...standaloneCard, event_summary: '海边散步看日落', _distance: 0.2 }],
    })
    const { wrapper } = mountSection([linkedCard])
    await wrapper.find('input').setValue('海边')
    await wrapper.find('input').trigger('keydown.enter')
    await flushPromises()
    expect(searchCards).toHaveBeenCalledWith('海边', 20)
    expect(wrapper.text()).toContain('海边散步看日落')
    expect(wrapper.text()).not.toContain('散步时想通了换工作的事')
  })

  it('expands a standalone card into a diary and navigates', async () => {
    const { wrapper, store } = mountSection([standaloneCard])
    await wrapper.find('.cards-section__action-btn').trigger('click')
    await flushPromises()
    expect(store.expandCard).toHaveBeenCalledWith('c2')
    expect(push).toHaveBeenCalledWith('/write/9')
  })

  it('deletes a card', async () => {
    const { wrapper, store } = mountSection([linkedCard])
    const del = wrapper.findAll('.cards-section__action-btn').at(-1)!
    await del.trigger('click')
    expect(store.removeCard).toHaveBeenCalledWith('c1')
  })
})
