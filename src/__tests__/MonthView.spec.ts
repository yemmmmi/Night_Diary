import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'

vi.mock('@/shared/api/diary', () => ({
  listDiaryEntries: vi.fn(async () => []),
}))
vi.mock('@/shared/api/plan', () => ({
  listTasks: vi.fn(async () => []),
  getTodayTasks: vi.fn(async () => []),
}))
vi.mock('@/shared/api/card', () => ({
  getMoodTrends: vi.fn(async () => []),
}))

import MonthView from '@/features/timeline/MonthView.vue'
import { useTimelineStore } from '@/stores/timeline'
import { toIsoDate } from '@/shared/utils/diaryFormat'
import type { DiaryEntry } from '@/shared/api/diary'

const todayIso = toIsoDate(new Date())

function makeEntry(id: number, date: string): DiaryEntry {
  return {
    id,
    content: 'x',
    date,
    weather: null,
    reply: null,
    created_at: date,
    updated_at: date,
  }
}

function mountView() {
  setActivePinia(createPinia())
  const store = useTimelineStore()
  const wrapper = mount(MonthView)
  return { wrapper, store }
}

describe('MonthView', () => {
  it('renders the anchor month label and highlights today', () => {
    const { wrapper } = mountView()
    const label = new Date().toLocaleDateString('zh-CN', { year: 'numeric', month: 'long' })
    expect(wrapper.text()).toContain(label)
    expect(wrapper.find(`[data-iso="${todayIso}"]`).classes()).toContain('is-today')
  })

  it('marks days with entries and jumps to day view on click', async () => {
    const { wrapper, store } = mountView()
    store.entries = [makeEntry(1, todayIso)]
    await nextTick()

    const todayCell = wrapper.find(`[data-iso="${todayIso}"]`)
    expect(todayCell.classes()).toContain('has-entry')

    const otherDay = toIsoDate(new Date(new Date().getFullYear(), new Date().getMonth(), 12))
    await wrapper.find(`[data-iso="${otherDay}"]`).trigger('click')
    expect(store.view).toBe('day')
    expect(store.date).toBe(otherDay)
  })
})
