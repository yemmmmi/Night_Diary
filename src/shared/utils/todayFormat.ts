import { parseLocalDate, weekdayLabel } from '@/shared/utils/diaryFormat'

const CN_DIGITS = ['零', '一', '二', '三', '四', '五', '六', '七', '八', '九'] as const
const CN_MONTHS = [
  '一月', '二月', '三月', '四月', '五月', '六月',
  '七月', '八月', '九月', '十月', '十一月', '十二月',
] as const

const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/

function isValidIso(iso: string): boolean {
  if (!ISO_DATE_RE.test(iso)) return false
  const date = parseLocalDate(iso)
  return !Number.isNaN(date.getTime())
}

/** 1–31 → 中文日（五号 / 十一日 / 二十日 / 三十一日，不含「一十」）。 */
function chineseDay(day: number): string {
  if (day < 1 || day > 31) return ''
  if (day < 10) return CN_DIGITS[day]
  if (day === 10) return '十'
  if (day < 20) return `十${CN_DIGITS[day % 10]}`
  const tens = Math.floor(day / 10)
  const rest = day % 10
  return rest === 0 ? `${CN_DIGITS[tens]}十` : `${CN_DIGITS[tens]}十${CN_DIGITS[rest]}`
}

/** 大日期头：八月三十一日。非法输入返回空串。 */
export function chineseDateLabel(iso: string): string {
  if (!isValidIso(iso)) return ''
  const date = parseLocalDate(iso)
  const month = CN_MONTHS[date.getMonth()]
  const day = chineseDay(date.getDate())
  return day ? `${month}${day}日` : ''
}

/** 副标题：2026 · 周一。非法输入返回空串。 */
export function todaySubtitle(iso: string): string {
  if (!isValidIso(iso)) return ''
  const date = parseLocalDate(iso)
  return `${date.getFullYear()} · ${weekdayLabel(date)}`
}
