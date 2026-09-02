import { describe, expect, it, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

const listPlansMock = vi.hoisted(() => vi.fn(async () => [] as unknown[]))
vi.mock('@/shared/api/plan', () => ({
  listPlans: listPlansMock,
  getTodayTasks: vi.fn(async () => []),
  createPlan: vi.fn(async () => ({})),
  createTask: vi.fn(async () => ({})),
  updateTaskStatus: vi.fn(async () => ({})),
  deletePlan: vi.fn(async () => {}),
}))

import PlanScene from '@/features/plan/PlanScene.vue'
import { usePlanStore } from '@/stores/plan'
import { toIsoDate } from '@/shared/utils/diaryFormat'
import type { PlanItem, TaskItem } from '@/shared/api/plan'

const todayIso = toIsoDate(new Date())
// 8 天前必然落在上一个 ISO 周（一周只有 7 天），保证「本周」口径可断言
const lastWeekIso = toIsoDate(new Date(Date.now() - 8 * 86_400_000))
const olderIso = toIsoDate(new Date(Date.now() - 15 * 86_400_000))

function task(partial: Partial<TaskItem> & { id: string }): TaskItem {
  return {
    plan_id: 'p1',
    title: 'task',
    note: null,
    link: null,
    due_date: null,
    status: 'done',
    source: 'manual',
    completed_at: null,
    actual_value: null,
    ...partial,
  }
}

function plan(partial: Partial<PlanItem> & { id: string }): PlanItem {
  return {
    title: '计划',
    motivation: null,
    source_refs: [],
    status: 'active',
    source: 'manual',
    tasks: [],
    recurrence: null,
    target_value: null,
    target_unit: null,
    target_period: null,
    template: null,
    today_progress: null,
    ...partial,
  }
}

/** 有 target 的账簿计划：今日 2.5 h、本周 2.5 / 4 h、累计 4 h（rate 0.625）。 */
const ledgerPlan: PlanItem = plan({
  id: 'p1',
  title: '早睡挑战',
  motivation: '想恢复精力',
  source: 'agent',
  source_refs: [{ type: 'diary', id: 7, date: '2026-08-12', snippet: '最近总是熬夜' }],
  recurrence: 'weekly:2,4',
  target_value: 4,
  target_unit: 'h',
  target_period: 'weekly',
  tasks: [
    task({ id: 't1', title: '23:30 前上床', status: 'pending' }),
    task({ id: 't2', title: '昨晚按时入睡', completed_at: `${todayIso}T22:00:00`, actual_value: 2.5 }),
    task({ id: 't3', title: '上周有一天早睡', completed_at: `${lastWeekIso}T22:00:00`, actual_value: 1.5 }),
  ],
})

/** 无 target 的事实计数计划：今日 1 · 本周 1 · 累计 4。 */
const countingPlan: PlanItem = plan({
  id: 'p2',
  title: '多散步',
  tasks: [
    task({ id: 't4', title: '午饭后走一圈', completed_at: `${todayIso}T13:00:00` }),
    task({ id: 't5', title: '上周散步一次', completed_at: `${lastWeekIso}T13:00:00` }),
    task({ id: 't6', title: '上周再走一次', completed_at: `${lastWeekIso}T18:00:00` }),
    task({ id: 't7', title: '更早的一次', completed_at: `${olderIso}T13:00:00` }),
  ],
})

const archivedPlan: PlanItem = plan({
  id: 'p9',
  title: '旧计划已归档',
  status: 'archived',
})

function mountScene(plans: PlanItem[] = []) {
  setActivePinia(createPinia())
  const store = usePlanStore()
  listPlansMock.mockResolvedValue(plans)
  store.plans = plans
  return { wrapper: mount(PlanScene), store }
}

describe('PlanScene', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('账簿行渲染周期印章与三档数字', () => {
    const { wrapper } = mountScene([ledgerPlan])
    expect(wrapper.find('[data-testid="plan-row"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="plan-stamp"]').text()).toContain('每周')
    const ledger = wrapper.find('[data-testid="plan-ledger"]')
    expect(ledger.exists()).toBe(true)
    expect(ledger.text()).toContain('今日')
    expect(ledger.text()).toContain('本周')
    expect(ledger.text()).toContain('累计')
    expect(ledger.text()).toContain('2.5')
    const bar = wrapper.find('[data-testid="plan-progress-bar"]')
    expect(bar.exists()).toBe(true)
    expect(bar.attributes('style')).toContain('62.5%')
  })

  it('无 target 的计划只显示事实计数（无进度条）', () => {
    const { wrapper } = mountScene([countingPlan])
    expect(wrapper.find('[data-testid="plan-progress-bar"]').exists()).toBe(false)
    const ledger = wrapper.find('[data-testid="plan-ledger"]')
    expect(ledger.text()).toContain('今日 1')
    expect(ledger.text()).toContain('本周 1')
    expect(ledger.text()).toContain('累计 4')
  })

  it('点击计划行展开任务明细与拉一条入口', async () => {
    const { wrapper } = mountScene([ledgerPlan])
    expect(wrapper.text()).not.toContain('23:30 前上床')
    await wrapper.find('[data-testid="plan-row"]').trigger('click')
    expect(wrapper.text()).toContain('23:30 前上床')
    expect(wrapper.text()).toContain('想恢复精力')
    expect(wrapper.text()).toContain('最近总是熬夜')
    expect(wrapper.find('.plan-refs').exists()).toBe(true)
    expect(wrapper.find('[data-testid="plan-pull-link"]').exists()).toBe(true)
  })

  it('拉一条提交后以计划标题预填创建今日待办', async () => {
    const api = await import('@/shared/api/plan')
    const { wrapper } = mountScene([ledgerPlan])
    await wrapper.find('[data-testid="plan-row"]').trigger('click')
    await wrapper.find('[data-testid="plan-pull-link"]').trigger('click')
    const input = wrapper.find('[data-testid="plan-pull-input"]')
    expect(input.exists()).toBe(true)
    expect((input.element as HTMLInputElement).value).toBe('早睡挑战')
    await input.setValue('读书 30 分钟')
    await input.trigger('keydown', { key: 'Enter' })
    await vi.waitFor(() => {
      expect(api.createTask).toHaveBeenCalledWith({
        plan_id: 'p1',
        title: '读书 30 分钟',
        due_date: todayIso,
      })
    })
  })

  it('完成任务时可记录实际值', async () => {
    const api = await import('@/shared/api/plan')
    const { wrapper } = mountScene([ledgerPlan])
    await wrapper.find('[data-testid="plan-row"]').trigger('click')
    const checkbox = wrapper.find('.plan-task input[type="checkbox"]')
    expect((checkbox.element as HTMLInputElement).checked).toBe(false)
    await checkbox.setValue(true)
    const actualInput = wrapper.find('[data-testid="task-actual-input"]')
    expect(actualInput.exists()).toBe(true)
    expect(wrapper.find('[data-testid="task-actual-skip"]').exists()).toBe(true)
    await actualInput.setValue('2.5')
    await wrapper.find('[data-testid="task-actual-confirm"]').trigger('click')
    await vi.waitFor(() => {
      expect(api.updateTaskStatus).toHaveBeenCalledWith('t1', 'done', 2.5)
    })
  })

  it('已归档计划折叠在底部', async () => {
    const { wrapper } = mountScene([ledgerPlan, archivedPlan])
    expect(wrapper.text()).not.toContain('旧计划已归档')
    expect(wrapper.findAll('[data-testid="plan-row"]')).toHaveLength(1)
    await wrapper.find('[data-testid="archived-toggle"]').trigger('click')
    expect(wrapper.text()).toContain('旧计划已归档')
  })

  it('no longer renders the today-todo section (moved to Today scene)', () => {
    const { wrapper } = mountScene([ledgerPlan])
    expect(wrapper.find('[data-testid="today-add-input"]').exists()).toBe(false)
  })

  it('shows a new-plan button that opens the create form', async () => {
    const { wrapper } = mountScene()
    expect(wrapper.find('.plan-create-form').exists()).toBe(false)
    await wrapper.find('[data-testid="new-plan-btn"]').trigger('click')
    expect(wrapper.find('.plan-create-form').exists()).toBe(true)
  })

  it('submits a manual plan with recurrence, target and tasks', async () => {
    const api = await import('@/shared/api/plan')
    const { wrapper } = mountScene()
    await wrapper.find('[data-testid="new-plan-btn"]').trigger('click')
    await wrapper.find('[data-testid="plan-title-input"]').setValue('早睡挑战')
    await wrapper.find('[data-testid="plan-motivation-input"]').setValue('想恢复精力')
    await wrapper.find('[data-testid="recurrence-weekly"]').trigger('click')
    await wrapper.find('[data-testid="weekday-chip-4"]').trigger('click')
    await wrapper.find('[data-testid="weekday-chip-2"]').trigger('click')
    await wrapper.find('[data-testid="target-value-input"]').setValue('4')
    await wrapper.find('[data-testid="target-unit-input"]').setValue('h')
    await wrapper.find('[data-testid="target-period-select"]').setValue('weekly')
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
          recurrence: 'weekly:2,4',
          target_value: 4,
          target_unit: 'h',
          target_period: 'weekly',
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
