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
}))

import PlanScene from '@/features/plan/PlanScene.vue'
import { usePlanStore } from '@/stores/plan'
import type { PlanItem } from '@/shared/api/plan'

const plan: PlanItem = {
  id: 'p1',
  title: '早睡挑战',
  motivation: null,
  source_refs: [{ type: 'diary', id: 7, date: '2026-08-12', snippet: '最近总是熬夜' }],
  status: 'active',
  source: 'agent',
  tasks: [],
}

function mountScene(plans: PlanItem[] = []) {
  setActivePinia(createPinia())
  const store = usePlanStore()
  store.plans = plans
  return { wrapper: mount(PlanScene), store }
}

describe('PlanScene', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders source refs block inside plan card', () => {
    const { wrapper } = mountScene([plan])
    expect(wrapper.find('.plan-refs').exists()).toBe(true)
    expect(wrapper.text()).toContain('最近总是熬夜')
  })

  it('no longer renders the today-todo section (moved to Today scene)', () => {
    const { wrapper } = mountScene([plan])
    expect(wrapper.text()).not.toContain('今日待办')
    expect(wrapper.find('[data-testid="today-add-input"]').exists()).toBe(false)
  })

  it('shows a new-plan button that opens the create form', async () => {
    const { wrapper } = mountScene()
    expect(wrapper.find('.plan-create-form').exists()).toBe(false)
    await wrapper.find('[data-testid="new-plan-btn"]').trigger('click')
    expect(wrapper.find('.plan-create-form').exists()).toBe(true)
  })

  it('submits a manual plan with title, motivation and tasks', async () => {
    const api = await import('@/shared/api/plan')
    const { wrapper } = mountScene()
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

  it('empty plans state offers both manual and AI entry points', () => {
    const { wrapper } = mountScene()
    expect(wrapper.find('[data-testid="plans-empty-manual"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="plans-empty-ai"]').exists()).toBe(true)
  })
})
