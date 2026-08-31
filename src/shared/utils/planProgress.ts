import type { PlanItem } from '@/shared/api/plan'
import { parseLocalDate, toIsoDate } from '@/shared/utils/diaryFormat'

const WEEKDAY_NAMES = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'] as const

function formatNumber(n: number): string {
  return Number.isInteger(n) ? String(n) : String(Math.round(n * 100) / 100)
}

/** ISO 周起始日（周一）的 ISO 日期串。 */
export function isoWeekStart(iso: string): string {
  const date = parseLocalDate(iso)
  const weekday = (date.getDay() + 6) % 7
  date.setDate(date.getDate() - weekday)
  return toIsoDate(date)
}

/** 周期标记转印章文案：'' / '每日' / '每周 · 周二 周四'。 */
export function recurrenceLabel(recurrence: string | null | undefined): string {
  if (!recurrence || recurrence === 'none') return ''
  if (recurrence === 'daily') return '每日'
  const match = /^weekly:([1-7](,[1-7])*)$/.exec(recurrence)
  if (!match) return ''
  const days = match[1].split(',').map((n) => WEEKDAY_NAMES[Number(n) - 1])
  return `每周 · ${days.join(' ')}`
}

export interface PlanProgress {
  today: number
  week: number
  total: number
  target: number | null
  unit: string | null
  period: 'daily' | 'weekly' | 'total' | null
  /** 完成率 0–1；无 target 时为 null。 */
  rate: number | null
}

/** 账簿式聚合（规格 §6.2）：今日/本周/累计 + 完成率。无实际值按 1 次计数。 */
export function summarizePlanProgress(plan: PlanItem, today: string): PlanProgress {
  const todayWeek = isoWeekStart(today)
  let day = 0
  let week = 0
  let total = 0
  for (const task of plan.tasks) {
    if (task.status !== 'done' || !task.completed_at) continue
    const value = task.actual_value ?? 1
    const date = task.completed_at.slice(0, 10)
    total += value
    if (date === today) day += value
    if (isoWeekStart(date) === todayWeek) week += value
  }
  const target = plan.target_value ?? null
  const period = plan.target_period ?? null
  let rate: number | null = null
  if (target != null && target > 0) {
    const base = period === 'daily' ? day : period === 'weekly' ? week : total
    rate = Math.min(base / target, 1)
  }
  return { today: day, week, total, target, unit: plan.target_unit ?? null, period, rate }
}

/** 账簿一行小字（规格 §5.3）：分母只落在目标对应档位；每日目标的本周档分母按 target × 7 换算。 */
export function ledgerLine(p: PlanProgress): string {
  const amount = (n: number): string => (p.unit ? `${formatNumber(n)} ${p.unit}` : formatNumber(n))
  const segment = (value: number, target: number | null): string =>
    target != null ? `${formatNumber(value)} / ${amount(target)}` : amount(value)
  const dayTarget = p.period === 'daily' ? p.target : null
  const weekTarget =
    p.period === 'weekly'
      ? p.target
      : p.period === 'daily' && p.target != null
        ? p.target * 7
        : null
  const totalTarget = p.period === 'total' ? p.target : null
  return [
    `今日 ${segment(p.today, dayTarget)}`,
    `本周 ${segment(p.week, weekTarget)}`,
    `累计 ${segment(p.total, totalTarget)}`,
  ].join(' · ')
}
