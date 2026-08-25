import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const { listDiaryEntries } = vi.hoisted(() => ({
  listDiaryEntries: vi.fn(async () => [
    {
      id: 1,
      content: 'a',
      date: '2026-08-25',
      weather: null,
      reply: null,
      created_at: '2026-08-25T10:00:00',
      updated_at: '2026-08-25T10:00:00',
    },
  ]),
}))

vi.mock('@/shared/api/diary', () => ({ listDiaryEntries }))
vi.mock('@/shared/api/card', () => ({
  listCards: vi.fn(async () => []),
  getMoodTrends: vi.fn(async () => []),
}))

import { useTimelineStore } from '@/stores/timeline'
import { listDiaryEntries as mockedList } from '@/shared/api/diary'

describe('timeline store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('starts on day view anchored at today', () => {
    const store = useTimelineStore()
    expect(store.view).toBe('day')
    expect(store.date).toBe(new Date().toISOString().slice(0, 10))
  })

  it('loads entries for the anchored day', async () => {
    const store = useTimelineStore()
    await store.setDate('2026-08-25')
    expect(mockedList).toHaveBeenCalledWith({
      date_from: '2026-08-25',
      date_to: '2026-08-25',
      limit: 100,
    })
    expect(store.entries).toHaveLength(1)
  })

  it('switching to week view loads the whole ISO week', async () => {
    const store = useTimelineStore()
    await store.setDate('2026-08-25') // 周二
    await store.setView('week')
    expect(mockedList).toHaveBeenLastCalledWith({
      date_from: '2026-08-24',
      date_to: '2026-08-30',
      limit: 100,
    })
  })

  it('shiftPeriod moves one day in day view and one week in week view', async () => {
    const store = useTimelineStore()
    await store.setDate('2026-08-25')
    await store.shiftPeriod(-1)
    expect(store.date).toBe('2026-08-24')

    await store.setView('week')
    await store.shiftPeriod(-1)
    expect(store.date).toBe('2026-08-17') // 前一周周一
  })

  it('month view range covers the whole anchor month', async () => {
    const store = useTimelineStore()
    await store.setDate('2026-08-15')
    await store.setView('month')
    expect(mockedList).toHaveBeenLastCalledWith({
      date_from: '2026-08-01',
      date_to: '2026-08-31',
      limit: 100,
    })
  })

  it('tracks the selected entry', async () => {
    const store = useTimelineStore()
    await store.setDate('2026-08-25')
    store.selectEntry(1)
    expect(store.selectedEntry?.id).toBe(1)
    store.selectEntry(null)
    expect(store.selectedEntry).toBeNull()
  })
})
