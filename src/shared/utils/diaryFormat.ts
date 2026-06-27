import type { DiaryEntry } from '@/shared/api/diary'

export type DiaryStatus = 'reply' | 'pending' | 'draft'

const WEEKDAY_LABELS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'] as const

export function parseLocalDate(isoDate: string): Date {
  const [y, m, d] = isoDate.split('-').map(Number)
  return new Date(y, m - 1, d)
}

export function toIsoDate(date: Date): string {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

export function startOfWeekMonday(reference: Date, weekOffset = 0): Date {
  const date = new Date(reference.getFullYear(), reference.getMonth(), reference.getDate())
  const day = date.getDay()
  const diff = day === 0 ? -6 : 1 - day
  date.setDate(date.getDate() + diff + weekOffset * 7)
  return date
}

export function endOfWeekSunday(weekStart: Date): Date {
  const end = new Date(weekStart)
  end.setDate(end.getDate() + 6)
  return end
}

export function formatWeekRangeLabel(weekStart: Date, weekEnd: Date): string {
  const startMonth = weekStart.getMonth() + 1
  const endMonth = weekEnd.getMonth() + 1
  const startDay = weekStart.getDate()
  const endDay = weekEnd.getDate()
  const year = weekStart.getFullYear()

  if (startMonth === endMonth) {
    return `${year}年${startMonth}月${startDay}日 - ${endDay}日`
  }
  return `${year}年${startMonth}月${startDay}日 - ${endMonth}月${endDay}日`
}

export function weekdayLabel(date: Date): string {
  return WEEKDAY_LABELS[date.getDay()]
}

export function diarySummary(
  content: string | null | undefined,
  maxLen = 28,
  fallback: string | null | undefined = '空白日记',
): string {
  const raw = (content ?? '').trim()
  if (!raw) return (fallback ?? '').trim() || '空白日记'
  const firstLine = (raw.split('\n')[0] ?? raw).replace(/\s+/g, ' ').trim()
  if (firstLine.length <= maxLen) return firstLine
  return `${firstLine.slice(0, maxLen)}…`
}

export function diaryStatus(entry: DiaryEntry): DiaryStatus {
  const text = (entry.content ?? '').trim()
  if (entry.ai_ans && entry.ai_ans.trim()) return 'reply'
  if (text.length < 12) return 'draft'
  return 'pending'
}

export function diaryStatusLabel(status: DiaryStatus): string {
  switch (status) {
    case 'reply':
      return '已有回信'
    case 'pending':
      return '待分析'
    case 'draft':
      return ''
  }
}

export function countWordUnits(text: string): number {
  return text.replace(/\s/g, '').length
}

export function computeWritingStreak(entries: DiaryEntry[]): number {
  const dates = new Set<string>()
  for (const entry of entries) {
    if (entry.date) dates.add(entry.date)
  }
  if (dates.size === 0) return 0

  const today = toIsoDate(new Date())
  const yesterday = toIsoDate(new Date(Date.now() - 86_400_000))

  let cursor: string | null = null
  if (dates.has(today)) cursor = today
  else if (dates.has(yesterday)) cursor = yesterday
  else return 0

  let streak = 0
  while (cursor && dates.has(cursor)) {
    streak += 1
    const prev = parseLocalDate(cursor)
    prev.setDate(prev.getDate() - 1)
    cursor = toIsoDate(prev)
  }
  return streak
}

export function groupEntriesForWeek(
  entries: DiaryEntry[],
  weekStart: Date,
  weekEnd: Date,
): { dayColumns: Map<string, DiaryEntry[]>; inbox: DiaryEntry[] } {
  const startIso = toIsoDate(weekStart)
  const endIso = toIsoDate(weekEnd)
  const dayColumns = new Map<string, DiaryEntry[]>()
  const inbox: DiaryEntry[] = []

  for (let i = 0; i < 7; i += 1) {
    const day = new Date(weekStart)
    day.setDate(day.getDate() + i)
    dayColumns.set(toIsoDate(day), [])
  }

  for (const entry of entries) {
    if (!entry.date) {
      inbox.push(entry)
      continue
    }
    if (entry.date < startIso || entry.date > endIso) {
      inbox.push(entry)
      continue
    }
    const bucket = dayColumns.get(entry.date)
    if (bucket) bucket.push(entry)
    else inbox.push(entry)
  }

  return { dayColumns, inbox }
}
