import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {}, params: {} }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

vi.mock('@/shared/api/diary', () => ({
  listDiaryEntries: vi.fn(async () => []),
}))
vi.mock('@/shared/api/plan', () => ({
  listTasks: vi.fn(async () => []),
  getTodayTasks: vi.fn(async () => []),
}))
vi.mock('@/shared/api/card', () => ({
  listCards: vi.fn(async () => []),
  getMoodTrends: vi.fn(async () => []),
}))
vi.mock('@/shared/api/weekly', () => ({
  listWeekly: vi.fn(async () => []),
  generateWeekly: vi.fn(async () => ({})),
  regenerateWeekly: vi.fn(async () => ({})),
}))
import TimelineScene from '@/pages/TimelineScene.vue'
import { useTimelineStore } from '@/stores/timeline'

function mountScene() {
  setActivePinia(createPinia())
  return { wrapper: mount(TimelineScene), timeline: useTimelineStore() }
}

describe('TimelineScene', () => {
  it('renders month view when view is month', async () => {
    const { wrapper, timeline } = mountScene()
    timeline.view = 'month'
    await nextTick()
    expect(wrapper.find('.month-view').exists()).toBe(true)
  })

  it('renders detail panel when an entry is selected', async () => {
    const { wrapper, timeline } = mountScene()
    timeline.entries = [
      {
        id: 3,
        content: 'x',
        date: '2026-08-25',
        weather: null,
        reply: null,
        created_at: '2026-08-25',
        updated_at: '2026-08-25',
      },
    ]
    timeline.selectEntry(3)
    await nextTick()
    expect(wrapper.find('.detail-panel').exists()).toBe(true)
  })
})
