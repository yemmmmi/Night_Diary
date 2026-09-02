/**
 * 技能生成的模板计划（PR8 三模板）进度视图：
 * 由 today_progress 快照计算账簿行与完成率，供 PlanScene 行级渲染。
 */

import type { PlanItem } from '@/shared/api/plan'

function formatNumber(n: number): string {
  return Number.isInteger(n) ? String(n) : String(Math.round(n * 100) / 100)
}

/** 秒数转「X小时Y分」式时长文案：3600 → 1小时，5400 → 1小时30分，720 → 12分钟。 */
export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  if (hours > 0) {
    return minutes > 0 ? `${hours}小时${minutes}分` : `${hours}小时`
  }
  return `${minutes}分钟`
}

/** 计划里已完成（done）的任务数与总数。 */
export function countDoneTasks(plan: PlanItem): { done: number; total: number } {
  const done = plan.tasks.filter((t) => t.status === 'done').length
  return { done, total: plan.tasks.length }
}

/**
 * 模板计划的账簿行（旧版计划请继续用 ledgerLine）。
 * - checkin_total：累计打卡 n/target 天
 * - timer_daily：今日时长 / 目标 · 连续坚持天数
 * - milestones：进度 done/total 个节点
 */
export function skillPlanLine(plan: PlanItem, liveSeconds?: number): string {
  const snapshot = plan.today_progress
  if (plan.template === 'checkin_total') {
    const total = snapshot?.total_checkins ?? 0
    const target = plan.target_value ?? 0
    return `累计打卡 ${total} / ${formatNumber(target)} ${plan.target_unit ?? '天'}`
  }
  if (plan.template === 'timer_daily') {
    const seconds =
      liveSeconds ?? snapshot?.today_seconds ?? 0
    const streak = snapshot?.streak_days ?? 0
    const target = plan.target_value ?? 0
    const targetLabel = formatNumber(target)
    return `今日 ${formatDuration(seconds)} / ${targetLabel}小时 · 连续坚持 ${streak} 天`
  }
  if (plan.template === 'milestones') {
    const { done, total } = countDoneTasks(plan)
    return `进度 ${done} / ${total} 个节点`
  }
  return ''
}

/** 模板计划完成率（0–1）；非模板计划或无目标时为 null。 */
export function skillPlanRate(plan: PlanItem, liveSeconds?: number): number | null {
  const snapshot = plan.today_progress
  if (plan.template === 'checkin_total') {
    const target = plan.target_value ?? 0
    if (target <= 0) return null
    return Math.min((snapshot?.total_checkins ?? 0) / target, 1)
  }
  if (plan.template === 'timer_daily') {
    const targetSeconds = snapshot?.target_seconds ?? (plan.target_value ?? 0) * 3600
    if (!targetSeconds || targetSeconds <= 0) return null
    const seconds = liveSeconds ?? snapshot?.today_seconds ?? 0
    return Math.min(seconds / targetSeconds, 1)
  }
  if (plan.template === 'milestones') {
    const { done, total } = countDoneTasks(plan)
    if (total <= 0) return null
    return done / total
  }
  return null
}
