import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/shared/api/plan', () => ({
  listPlans: vi.fn(async () => []),
  getTodayTasks: vi.fn(async () => []),
  updateTaskStatus: vi.fn(async () => ({})),
  deleteTask: vi.fn(async () => undefined),
  deletePlan: vi.fn(async () => undefined),
}))

import TaskFoldRow from '@/features/timeline/TaskFoldRow.vue'
import { usePlanStore } from '@/stores/plan'

function mountRow() {
  setActivePinia(createPinia())
  const planStore = usePlanStore()
  planStore.todayTasks = [
    { id: 't1', plan_id: null, title: '散步', note: null, due_date: null, status: 'pending', source: 'manual', completed_at: null },
    { id: 't2', plan_id: null, title: '读书', note: null, due_date: null, status: 'done', source: 'manual', completed_at: null },
  ] as never
  const toggleSpy = vi.spyOn(planStore, 'toggleTask').mockImplementation(async () => {})
  const wrapper = mount(TaskFoldRow, { global: { plugins: [] } })
  return { wrapper, toggleSpy }
}

describe('TaskFoldRow', () => {
  it('hides entirely when there are no tasks', async () => {
    setActivePinia(createPinia())
    const planStore = usePlanStore()
    planStore.todayTasks = []
    const wrapper = mount(TaskFoldRow)
    expect(wrapper.find('.task-fold').exists()).toBe(false)
  })

  it('renders a neutral summary line and expands on click', async () => {
    const { wrapper } = mountRow()
    expect(wrapper.text()).toContain('今日 2 项 · 已完成 1')
    expect(wrapper.find('[data-testid="ink-check"]').exists()).toBe(false)

    await wrapper.find('.task-fold__summary').trigger('click')
    expect(wrapper.findAll('[data-testid="ink-check"]')).toHaveLength(2)
  })

  it('toggles a task through the plan store when the ink check is clicked', async () => {
    const { wrapper, toggleSpy } = mountRow()
    await wrapper.find('.task-fold__summary').trigger('click')
    const first = wrapper.findAll('[data-testid="ink-check"]')[0]
    await first.trigger('click')
    expect(toggleSpy).toHaveBeenCalledWith('t1', 'pending')
  })

  it('marks done rows with the ink strike line', async () => {
    const { wrapper } = mountRow()
    await wrapper.find('.task-fold__summary').trigger('click')
    const items = wrapper.findAll('.task-fold__item')
    expect(items[0].classes()).not.toContain('is-done')
    expect(items[1].classes()).toContain('is-done')
    expect(items[1].find('.task-fold__title.ink-strike').exists()).toBe(true)
  })
})
