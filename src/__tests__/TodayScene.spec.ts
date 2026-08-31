import { describe, expect, it, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'

const push = vi.fn()

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {}, params: {} }),
  useRouter: () => ({ push }),
}))

const listDiaryEntries = vi.hoisted(() => vi.fn(async () => [] as unknown[]))
vi.mock('@/shared/api/diary', () => ({
  listDiaryEntries,
}))
vi.mock('@/shared/api/plan', () => ({
  listPlans: vi.fn(async () => []),
  getTodayTasks: vi.fn(async () => []),
  createTask: vi.fn(async () => ({})),
}))
vi.mock('@/shared/api/card', () => ({
  listCards: vi.fn(async () => []),
}))

import TodayScene from '@/pages/TodayScene.vue'
import { usePlanStore } from '@/stores/plan'
import { useCardStore } from '@/stores/card'
import { toIsoDate } from '@/shared/utils/diaryFormat'
import type { DiaryEntry } from '@/shared/api/diary'
import type { PlanItem, TaskItem } from '@/shared/api/plan'

const todayIso = toIsoDate(new Date())

function entry(id: number, date: string, content: string): DiaryEntry {
  return { id, content, date, weather: null, reply: null, created_at: `${date}T21:00:00`, updated_at: `${date}T21:00:00` }
}

function task(id: string, planId: string | null, title: string): TaskItem {
  return { id, plan_id: planId, title, note: null, due_date: todayIso, status: 'pending', source: 'manual', completed_at: null }
}

function plan(id: string, title: string, motivation: string | null): PlanItem {
  return { id, title, motivation, source_refs: [], status: 'active', source: 'manual', tasks: [] }
}

function mountScene() {
  setActivePinia(createPinia())
  const planStore = usePlanStore()
  const cardStore = useCardStore()
  return { wrapper: mount(TodayScene), planStore, cardStore }
}

describe('TodayScene', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listDiaryEntries.mockResolvedValue([])
  })

  it('renders the serif big date header with prev/next paging', async () => {
    const { wrapper } = mountScene()
    await flushPromises()
    expect(wrapper.find('[data-testid="today-big-date"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="today-prev"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="today-next"]').exists()).toBe(true)
  })

  it('shows the blank-paper empty state when the day has no entry', async () => {
    const { wrapper } = mountScene()
    await flushPromises()
    expect(wrapper.text()).toContain('这一页还是空白')
    const write = wrapper.find('[data-testid="today-write-cta"]')
    expect(write.exists()).toBe(true)
    await write.trigger('click')
    expect(push).toHaveBeenCalledWith('/write')
  })

  it('renders diary entries for the anchored date', async () => {
    listDiaryEntries.mockResolvedValue([entry(7, todayIso, '今天走了很久，想通了一些事。')])
    const { wrapper } = mountScene()
    await flushPromises()
    expect(wrapper.text()).toContain('今天走了很久')
    expect(wrapper.text()).not.toContain('这一页还是空白')
  })

  it('lists today tasks with their plan origin label', async () => {
    const { wrapper, planStore } = mountScene()
    planStore.plans = [plan('p1', '备战秋招', null)]
    planStore.todayTasks = [task('t1', 'p1', '刷一套行测'), task('t2', null, '倒垃圾')]
    await nextTick()
    const rows = wrapper.findAll('[data-testid="today-task-row"]')
    expect(rows).toHaveLength(2)
    expect(wrapper.text()).toContain('刷一套行测')
    expect(wrapper.text()).toContain('备战秋招')
    expect(wrapper.text()).toContain('倒垃圾')
  })

  it('shows active plans with motivation in the right rail', async () => {
    const { wrapper, planStore } = mountScene()
    planStore.plans = [
      plan('p1', '备战秋招', '想进一家好公司'),
      plan('p2', '已归档的事', null),
    ]
    planStore.plans[1].status = 'archived'
    await nextTick()
    expect(wrapper.text()).toContain('备战秋招')
    expect(wrapper.text()).toContain('想进一家好公司')
    expect(wrapper.text()).not.toContain('已归档的事')
  })

  it('creates a standalone today task via the quick-add input', async () => {
    const api = await import('@/shared/api/plan')
    const { wrapper } = mountScene()
    await flushPromises()
    await wrapper.find('[data-testid="today-add-input"]').setValue('晚上散步 20 分钟')
    await wrapper.find('[data-testid="today-add-btn"]').trigger('click')
    await vi.waitFor(() => {
      expect(api.createTask).toHaveBeenCalledWith(
        expect.objectContaining({ title: '晚上散步 20 分钟', due_date: todayIso }),
      )
    })
  })
})
