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
    expect(wrapper.find('input[type="checkbox"]').exists()).toBe(false)

    await wrapper.find('.task-fold__summary').trigger('click')
    expect(wrapper.findAll('input[type="checkbox"]')).toHaveLength(2)
  })

  it('toggles a task through the plan store', async () => {
    const { wrapper, toggleSpy } = mountRow()
    await wrapper.find('.task-fold__summary').trigger('click')
    const first = wrapper.findAll('input[type="checkbox"]')[0]
    await first.setValue(true)
    expect(toggleSpy).toHaveBeenCalledWith('t1', 'pending')
  })
})
