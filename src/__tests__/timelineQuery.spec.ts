import { describe, expect, it } from 'vitest'

import { buildTimelineQuery, parseTimelineQuery } from '@/shared/utils/timelineQuery'

describe('timelineQuery', () => {
  it('defaults to day view and the given today', () => {
    expect(parseTimelineQuery({}, '2026-08-25')).toEqual({ view: 'day', date: '2026-08-25' })
  })

  it('parses view and date from the query', () => {
    const parsed = parseTimelineQuery({ view: 'week', date: '2026-08-24' }, '2026-08-25')
    expect(parsed).toEqual({ view: 'week', date: '2026-08-24' })
  })

  it('falls back on invalid view or malformed date', () => {
    const parsed = parseTimelineQuery({ view: 'year', date: '08/25' }, '2026-08-25')
    expect(parsed).toEqual({ view: 'day', date: '2026-08-25' })
  })

  it('handles repeated query params (array form)', () => {
    const parsed = parseTimelineQuery({ view: ['month'], date: ['2026-08-01'] }, '2026-08-25')
    expect(parsed).toEqual({ view: 'month', date: '2026-08-01' })
  })

  it('builds a query object for the router', () => {
    expect(buildTimelineQuery('week', '2026-08-24')).toEqual({ view: 'week', date: '2026-08-24' })
  })
})
