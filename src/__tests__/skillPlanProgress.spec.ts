import { describe, expect, it } from 'vitest'

import {
  countDoneTasks,
  formatDuration,
  planSourceSummary,
  skillPlanLine,
  skillPlanPercentLabel,
  skillPlanRate,
} from '@/shared/utils/skillPlanProgress'
import type { PlanItem, TaskItem } from '@/shared/api/plan'

function task(id: string, status: TaskItem['status']): TaskItem {
  return {
    id,
    plan_id: 'p1',
    title: `节点 ${id}`,
    note: null,
    link: null,
    due_date: null,
    status,
    source: 'agent',
    completed_at: null,
    actual_value: null,
  }
}

function planWith(extra: Partial<PlanItem>): PlanItem {
  return {
    id: 'p1',
    title: '坚持减肥30天',
    motivation: null,
    source_refs: [],
    status: 'active',
    source: 'agent',
    tasks: [],
    recurrence: null,
    target_value: null,
    target_unit: null,
    target_period: null,
    template: null,
    today_progress: null,
    ...extra,
  } as PlanItem
}

function checkinPlan(total: number): PlanItem {
  return planWith({
    template: 'checkin_total',
    target_value: 30,
    target_unit: '天',
    target_period: 'total',
    today_progress: { checkin_date: '2026-09-02', total_checkins: total },
  })
}

function timerPlan(seconds: number, streak = 0): PlanItem {
  return planWith({
    template: 'timer_daily',
    target_value: 4,
    target_unit: '小时',
    target_period: 'daily',
    today_progress: {
      checkin_date: '2026-09-02',
      today_seconds: seconds,
      target_seconds: 14400,
      streak_days: streak,
    },
  })
}

describe('formatDuration', () => {
  it('formats hours, hours+minutes and minutes-only durations', () => {
    expect(formatDuration(3600)).toBe('1小时')
    expect(formatDuration(5400)).toBe('1小时30分')
    expect(formatDuration(720)).toBe('12分钟')
    expect(formatDuration(0)).toBe('0分钟')
  })

  it('floors fractional seconds and clamps negatives to zero', () => {
    expect(formatDuration(719.9)).toBe('11分钟')
    expect(formatDuration(-100)).toBe('0分钟')
  })
})

describe('skillPlanLine', () => {
  it('renders the cumulative check-in ledger for checkin_total', () => {
    expect(skillPlanLine(checkinPlan(5))).toBe('累计打卡 5 / 30 天')
  })

  it('renders today duration, target and streak for timer_daily', () => {
    expect(skillPlanLine(timerPlan(5400, 2))).toBe('今日 1小时30分 / 4小时 · 连续坚持 2 天')
  })

  it('prefers live seconds over the snapshot for timer_daily', () => {
    expect(skillPlanLine(timerPlan(0), 7200)).toBe('今日 2小时 / 4小时 · 连续坚持 0 天')
  })

  it('renders done-node counts for milestones', () => {
    const plan = planWith({
      template: 'milestones',
      tasks: [task('t1', 'done'), task('t2', 'done'), task('t3', 'pending')],
    })
    expect(skillPlanLine(plan)).toBe('进度 2 / 3 个节点')
  })

  it('returns an empty line for legacy plans without a template', () => {
    expect(skillPlanLine(planWith({}))).toBe('')
  })
})

describe('skillPlanRate', () => {
  it('computes checkin progress and caps it at 1', () => {
    expect(skillPlanRate(checkinPlan(15))).toBe(0.5)
    expect(skillPlanRate(checkinPlan(30))).toBe(1)
    expect(skillPlanRate(checkinPlan(42))).toBe(1)
  })

  it('computes timer progress from live seconds and caps it at 1', () => {
    expect(skillPlanRate(timerPlan(0), 7200)).toBe(0.5)
    expect(skillPlanRate(timerPlan(14400))).toBe(1)
    expect(skillPlanRate(timerPlan(20000))).toBe(1)
  })

  it('computes node completion for milestones', () => {
    const plan = planWith({
      template: 'milestones',
      tasks: [task('t1', 'done'), task('t2', 'pending'), task('t3', 'pending'), task('t4', 'pending'), task('t5', 'pending')],
    })
    expect(skillPlanRate(plan)).toBe(0.2)
  })

  it('returns null for legacy plans or missing targets', () => {
    expect(skillPlanRate(planWith({}))).toBeNull()
    const noTarget = planWith({
      template: 'checkin_total',
      target_value: null,
      today_progress: { checkin_date: '2026-09-02', total_checkins: 3 },
    })
    expect(skillPlanRate(noTarget)).toBeNull()
    const noNodes = planWith({ template: 'milestones', tasks: [] })
    expect(skillPlanRate(noNodes)).toBeNull()
  })
})

describe('countDoneTasks', () => {
  it('counts done tasks against the total', () => {
    const plan = planWith({
      tasks: [task('t1', 'done'), task('t2', 'pending'), task('t3', 'done')],
    })
    expect(countDoneTasks(plan)).toEqual({ done: 2, total: 3 })
  })
})

describe('skillPlanPercentLabel', () => {
  it('renders "X / 30 天 (Z%)" for checkin_total', () => {
    expect(skillPlanPercentLabel(checkinPlan(0))).toBe('0 / 30 天 (0%)')
    expect(skillPlanPercentLabel(checkinPlan(15))).toBe('15 / 30 天 (50%)')
    expect(skillPlanPercentLabel(checkinPlan(30))).toBe('30 / 30 天 (100%)')
  })

  it('renders "X小时 / 4小时 (Z%)" for timer_daily', () => {
    expect(skillPlanPercentLabel(timerPlan(7200))).toBe('2小时 / 4小时 (50%)')
    expect(skillPlanPercentLabel(timerPlan(0), 7200)).toBe('2小时 / 4小时 (50%)')
  })

  it('renders "X / Y 节点 (Z%)" for milestones', () => {
    const plan = planWith({
      template: 'milestones',
      tasks: [task('t1', 'done'), task('t2', 'pending'), task('t3', 'pending')],
    })
    expect(skillPlanPercentLabel(plan)).toBe('1 / 3 节点 (33%)')
  })

  it('returns null for legacy plans or missing targets', () => {
    expect(skillPlanPercentLabel(planWith({}))).toBeNull()
    const noTarget = planWith({
      template: 'checkin_total',
      target_value: null,
      today_progress: { checkin_date: '2026-09-02', total_checkins: 3 },
    })
    expect(skillPlanPercentLabel(noTarget)).toBeNull()
  })
})

describe('planSourceSummary', () => {
  it('aggregates queries, multi-source nodes and deduped domains', () => {
    const plan = planWith({
      template: 'milestones',
      tasks: [
        task('t1', 'pending'),
        task('t2', 'pending'),
        task('t3', 'pending'),
      ] as TaskItem[],
    })
    plan.tasks[0].source_links = [
      { url: 'https://a.com/x', domain: 'a.com', multi_source: true },
      { url: 'https://b.com/y', domain: 'b.com', multi_source: true },
    ]
    plan.tasks[1].source_links = [
      { url: 'https://a.com/z', domain: 'a.com', multi_source: true },
    ]
    const summary = planSourceSummary(plan)
    expect(summary.used).toBe(2)
    expect(summary.multiSource).toBe(2)
    expect(summary.totalNodes).toBe(3)
    expect(summary.domains).toEqual(['a.com', 'b.com'])
  })

  it('returns zeros when no node has sources', () => {
    const plan = planWith({ template: 'milestones', tasks: [task('t1', 'pending')] })
    const summary = planSourceSummary(plan)
    expect(summary).toEqual({ used: 0, multiSource: 0, totalNodes: 1, domains: [] })
  })
})
