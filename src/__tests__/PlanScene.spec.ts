import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('@/shared/api/plan', () => ({
  listPlans: vi.fn(async () => []),
  getTodayTasks: vi.fn(async () => []),
}))

import PlanScene from '@/features/plan/PlanScene.vue'
import { usePlanStore } from '@/stores/plan'
import { toIsoDate } from '@/shared/utils/diaryFormat'
import type { PlanItem, TaskItem } from '@/shared/api/plan'

const plan: PlanItem = {
  id: 'p1',
  title: '早睡挑战',
  motivation: null,
  source_refs: [{ type: 'diary', id: 7, date: '2026-08-12', snippet: '最近总是熬夜' }],
  status: 'active',
  source: 'agent',
  tasks: [],
}

const yesterday = toIsoDate(new Date(Date.now() - 86400000))
const tomorrow = toIsoDate(new Date(Date.now() + 86400000))

function task(id: string, due: string | null, status: TaskItem['status'] = 'pending'): TaskItem {
  return { id, plan_id: 'p1', title: `任务${id}`, note: null, due_date: due, status, source: 'manual', completed_at: null }
}

function mountScene(plans: PlanItem[] = [], todayTasks: TaskItem[] = []) {
  setActivePinia(createPinia())
  const store = usePlanStore()
  store.plans = plans
  store.todayTasks = todayTasks
  return { wrapper: mount(PlanScene), store }
}

describe('PlanScene', () => {
  it('renders source refs block inside plan card', () => {
    const { wrapper } = mountScene([plan])
    expect(wrapper.find('.plan-refs').exists()).toBe(true)
    expect(wrapper.text()).toContain('最近总是熬夜')
  })

  it('marks overdue tasks neutral gray without red', () => {
    const { wrapper } = mountScene([], [task('t1', yesterday), task('t2', tomorrow)])
    const rows = wrapper.findAll('.task-row')
    expect(rows[0].classes()).toContain('is-overdue')
    expect(rows[1].classes()).not.toContain('is-overdue')
  })

  it('does not mark done tasks overdue', () => {
    const { wrapper } = mountScene([], [task('t1', yesterday, 'done')])
    expect(wrapper.find('.task-row').classes()).not.toContain('is-overdue')
  })
})
