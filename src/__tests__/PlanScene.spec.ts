import { describe, expect, it, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('@/shared/api/plan', () => ({
  listPlans: vi.fn(async () => []),
  getTodayTasks: vi.fn(async () => []),
  createPlan: vi.fn(async () => ({})),
  createTask: vi.fn(async () => ({})),
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

describe('PlanScene manual creation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows a new-plan button that opens the create form', async () => {
    const { wrapper } = mountScene()
    expect(wrapper.find('.plan-create-form').exists()).toBe(false)

    await wrapper.find('[data-testid="new-plan-btn"]').trigger('click')
    expect(wrapper.find('.plan-create-form').exists()).toBe(true)
  })

  it('submits a manual plan with title, motivation and tasks', async () => {
    const api = await import('@/shared/api/plan')
    const { wrapper, store } = mountScene()

    await wrapper.find('[data-testid="new-plan-btn"]').trigger('click')
    await wrapper.find('[data-testid="plan-title-input"]').setValue('早睡挑战')
    await wrapper.find('[data-testid="plan-motivation-input"]').setValue('想恢复精力')
    await wrapper.find('[data-testid="form-add-task"]').trigger('click')
    const taskInputs = wrapper.findAll('[data-testid="task-title-input"]')
    await taskInputs[0].setValue('23:30 前上床')
    await wrapper.find('[data-testid="plan-submit"]').trigger('click')

    await vi.waitFor(() => {
      expect(api.createPlan).toHaveBeenCalledWith(
        expect.objectContaining({
          title: '早睡挑战',
          motivation: '想恢复精力',
          source: 'manual',
          tasks: [expect.objectContaining({ title: '23:30 前上床' })],
        }),
      )
    })
    await vi.waitFor(() => {
      expect(wrapper.find('.plan-create-form').exists()).toBe(false)
    })
    expect(store.plans).toEqual([])
  })

  it('blocks submit when title is empty', async () => {
    const api = await import('@/shared/api/plan')
    const { wrapper } = mountScene()

    await wrapper.find('[data-testid="new-plan-btn"]').trigger('click')
    await wrapper.find('[data-testid="plan-submit"]').trigger('click')

    await new Promise((r) => setTimeout(r, 0))
    expect(api.createPlan).not.toHaveBeenCalled()
    expect(wrapper.find('.plan-create-form').exists()).toBe(true)
  })

  it('creates a standalone today task via quick add', async () => {
    const api = await import('@/shared/api/plan')
    const { wrapper } = mountScene()
    const todayIso = toIsoDate(new Date())

    await wrapper.find('[data-testid="today-add-input"]').setValue('晚上散步 20 分钟')
    await wrapper.find('[data-testid="today-add-btn"]').trigger('click')

    await vi.waitFor(() => {
      expect(api.createTask).toHaveBeenCalledWith(
        expect.objectContaining({ title: '晚上散步 20 分钟', due_date: todayIso }),
      )
    })
    await vi.waitFor(() => {
      expect(
        (wrapper.find('[data-testid="today-add-input"]').element as HTMLInputElement).value,
      ).toBe('')
    })
  })

  it('empty plans state offers both manual and AI entry points', () => {
    const { wrapper } = mountScene()
    expect(wrapper.find('[data-testid="plans-empty-manual"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="plans-empty-ai"]').exists()).toBe(true)
  })
})
