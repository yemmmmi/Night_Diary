import type { LocationQuery, LocationQueryRaw } from 'vue-router'

export type TimelineView = 'day' | 'week' | 'month'

const VIEWS: readonly TimelineView[] = ['day', 'week', 'month']

const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/

export function isTimelineView(value: unknown): value is TimelineView {
  return typeof value === 'string' && (VIEWS as readonly string[]).includes(value)
}

function firstQueryValue(value: LocationQuery[string]): unknown {
  return Array.isArray(value) ? value[0] : value
}

export function parseTimelineQuery(
  query: LocationQuery,
  todayIso: string,
): { view: TimelineView; date: string } {
  const rawView = firstQueryValue(query.view)
  const view = isTimelineView(rawView) ? rawView : 'day'
  const rawDate = firstQueryValue(query.date)
  const date =
    typeof rawDate === 'string' && ISO_DATE_RE.test(rawDate) ? rawDate : todayIso
  return { view, date }
}

export function buildTimelineQuery(view: TimelineView, date: string): LocationQueryRaw {
  return { view, date }
}
