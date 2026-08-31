import { describe, expect, it } from 'vitest'

import { isoWeekStart, recurrenceLabel, summarizePlanProgress } from '@/shared/utils/planProgress'
import type { PlanItem } from '@/shared/api/plan'

function planWith(
  tasks: Array<Partial<PlanItem['tasks'][number]>>,
  extra: Partial<PlanItem> = {},
): PlanItem {
  return {
    id: 'p1',
    title: '早睡挑战',
    motivation: null,
    source_refs: [],
    status: 'active',
    source: 'manual',
    tasks: tasks.map((t, i) => ({
      id: `t${i}`,
      plan_id: 'p1',
      title: t.title ?? 'task',
      note: null,
      due_date: null,
      status: t.status ?? 'done',
      source: 'manual',
      completed_at: t.completed_at ?? null,
      actual_value: t.actual_value ?? null,
    })),
    recurrence: null,
    target_value: null,
    target_unit: null,
    target_period: null,
    ...extra,
  } as PlanItem
}

describe('isoWeekStart', () => {
  it('returns Monday of the week', () => {
    // 2026-08-31 is Monday; 2026-09-03 (Thursday) belongs to that week.
    expect(isoWeekStart('2026-09-03')).toBe('2026-08-31')
    expect(isoWeekStart('2026-08-31')).toBe('2026-08-31')
    // 2026-08-30 (Sunday) belongs to the previous week starting 2026-08-24.
    expect(isoWeekStart('2026-08-30')).toBe('2026-08-24')
  })
})

describe('recurrenceLabel', () => {
  it('labels none/daily/weekly', () => {
    expect(recurrenceLabel(null)).toBe('')
    expect(recurrenceLabel('none')).toBe('')
    expect(recurrenceLabel('daily')).toBe('每日')
    expect(recurrenceLabel('weekly:2,4')).toBe('每周 · 周二 周四')
    expect(recurrenceLabel('weekly:7')).toBe('每周 · 周日')
    expect(recurrenceLabel('garbage')).toBe('')
  })
})

describe('summarizePlanProgress', () => {
  const today = '2026-08-31'

  it('sums actual values of tasks completed today', () => {
    const plan = planWith([
      { completed_at: '2026-08-31T21:00:00', actual_value: 2.5 },
      { completed_at: '2026-08-31T22:00:00', actual_value: null },
      { completed_at: '2026-08-30T21:00:00', actual_value: 1 },
    ])
    const p = summarizePlanProgress(plan, today)
    expect(p.today).toBe(3.5)
    expect(p.total).toBe(4.5)
  })

  it('sums this ISO week separately from last week', () => {
    const plan = planWith([
      { completed_at: '2026-08-31T09:00:00', actual_value: 1 },
      { completed_at: '2026-08-30T09:00:00', actual_value: 1 },
    ])
    const p = summarizePlanProgress(plan, today)
    expect(p.week).toBe(1)
    expect(p.total).toBe(2)
  })

  it('ignores pending tasks and computes rate against target period', () => {
    const plan = planWith(
      [{ status: 'pending', completed_at: null, actual_value: 2 }],
      { target_value: 4, target_unit: 'h', target_period: 'daily' },
    )
    const p = summarizePlanProgress(plan, today)
    expect(p.today).toBe(0)
    expect(p.rate).toBe(0)
    expect(p.target).toBe(4)
    expect(p.unit).toBe('h')
  })

  it('caps rate at 1 and hides rate without target', () => {
    const plan = planWith([{ completed_at: '2026-08-31T09:00:00', actual_value: 9 }])
    const withTarget = summarizePlanProgress(
      planWith([{ completed_at: '2026-08-31T09:00:00', actual_value: 9 }], {
        target_value: 4,
        target_period: 'daily',
      }),
      today,
    )
    expect(withTarget.rate).toBe(1)
    const noTarget = summarizePlanProgress(plan, today)
    expect(noTarget.rate).toBeNull()
    expect(noTarget.target).toBeNull()
  })

  it('weekly target rate uses the week sum', () => {
    const plan = planWith(
      [
        { completed_at: '2026-08-31T09:00:00', actual_value: 2 },
        { completed_at: '2026-08-30T09:00:00', actual_value: 1 },
      ],
      { target_value: 6, target_period: 'weekly' },
    )
    const p = summarizePlanProgress(plan, today)
    expect(p.week).toBe(2)
    expect(p.rate).toBe(1 / 3)
  })
})
