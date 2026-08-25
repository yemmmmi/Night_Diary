import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import type { WeeklyReport } from '@/shared/api/weekly'

const push = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}))

vi.mock('@/shared/api/weekly', () => ({
  listWeekly: vi.fn(async () => []),
  getLatestWeekly: vi.fn(async () => null),
  generateWeekly: vi.fn(async () => ({})),
  regenerateWeekly: vi.fn(async () => ({})),
  deleteWeekly: vi.fn(async () => undefined),
}))

import WeeklyLetterCard from '@/features/timeline/WeeklyLetterCard.vue'
import { useWeeklyStore } from '@/stores/weekly'
import { usePlanStore } from '@/stores/plan'

const report = {
  id: 9,
  period_start: '2026-08-24',
  period_end: '2026-08-30',
  content: '这一周你经历了许多。',
  diary_count: 3,
  card_count: 5,
  avg_mood: 0.6,
  token_cost: 800,
  execution_tier: 'medium',
  created_at: '2026-08-30T20:00:00',
  plan_executions: [
    {
      plan_id: 'p1',
      title: '早睡挑战',
      done: 1,
      total: 2,
      source_refs: [{ type: 'diary', id: 7, date: '2026-08-24' }],
    },
  ],
  week_tasks: [
    { task_id: 't1', title: '周末散步', status: 'pending', source: 'agent', due_date: null },
  ],
} as unknown as WeeklyReport

function mountCard(weekStartIso: string, reports: WeeklyReport[] = []) {
  setActivePinia(createPinia())
  const weeklyStore = useWeeklyStore()
  const planStore = usePlanStore()
  planStore.toggleTask = vi.fn(async () => {})
  weeklyStore.reports = reports
  return {
    wrapper: mount(WeeklyLetterCard, { props: { weekStartIso } }),
    weeklyStore,
    planStore,
  }
}

describe('WeeklyLetterCard', () => {
  it('offers generation only for the current week when no report exists', () => {
    const future = mountCard('2099-01-04') // far future week = not current
    expect(future.wrapper.text()).toContain('这一周没有留下周信')
    expect(future.wrapper.text()).not.toContain('生成本周周记')

    const current = mountCard(currentMondayIso())
    expect(current.wrapper.text()).toContain('生成本周周记')
  })

  it('renders the letter with structured plan block', () => {
    const { wrapper } = mountCard(report.period_start, [report])
    expect(wrapper.text()).toContain('这一周你经历了许多。')
    expect(wrapper.text()).toContain('早睡挑战')
    expect(wrapper.text()).toContain('1/2')
    expect(wrapper.text()).toContain('周末散步')
    expect(wrapper.text()).toContain('AI 建议')
  })

  it('falls back to plain content for legacy reports without structured data', () => {
    const legacy = {
      ...report,
      plan_executions: [],
      week_tasks: [],
    } as unknown as WeeklyReport
    const { wrapper } = mountCard(legacy.period_start, [legacy])
    expect(wrapper.text()).toContain('这一周你经历了许多。')
    expect(wrapper.find('.letter-plan').exists()).toBe(false)
  })

  it('toggles week tasks through the plan store and updates locally', async () => {
    const { wrapper, planStore } = mountCard(report.period_start, [report])
    await wrapper.find('.letter-plan__task input[type="checkbox"]').setValue(true)
    expect(planStore.toggleTask).toHaveBeenCalledWith('t1', 'pending')
  })
})

function currentMondayIso(): string {
  const now = new Date()
  const day = now.getDay()
  const diff = day === 0 ? -6 : 1 - day
  const monday = new Date(now.getFullYear(), now.getMonth(), now.getDate() + diff)
  return `${monday.getFullYear()}-${String(monday.getMonth() + 1).padStart(2, '0')}-${String(monday.getDate()).padStart(2, '0')}`
}
