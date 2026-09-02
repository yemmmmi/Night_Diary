import { describe, expect, it } from 'vitest'

import { parseServerTime, serverDateIso, serverTimeLabel } from '@/shared/utils/timeFormat'

describe('parseServerTime', () => {
  it('treats timezone-less server timestamps as UTC', () => {
    // 服务器存 naive UTC：2026-09-01T16:30:00Z
    const date = parseServerTime('2026-09-01T16:30:00')
    expect(date.toISOString()).toBe('2026-09-01T16:30:00.000Z')
  })

  it('keeps explicit Z-suffixed timestamps intact', () => {
    const date = parseServerTime('2026-09-01T16:30:00.000Z')
    expect(date.toISOString()).toBe('2026-09-01T16:30:00.000Z')
  })

  it('keeps offset-bearing timestamps intact', () => {
    const date = parseServerTime('2026-09-01T16:30:00+02:00')
    expect(date.toISOString()).toBe('2026-09-01T14:30:00.000Z')
  })

  it('returns Invalid Date for garbage input', () => {
    expect(Number.isNaN(parseServerTime('not-a-date').getTime())).toBe(true)
  })
})

describe('serverDateIso', () => {
  it('returns the LOCAL calendar date of a naive UTC timestamp', () => {
    // UTC 9月1日 16:30 = 北京 9月2日 00:30 → 本地日期应为 09-02
    const local = process.env.TZ
    try {
      process.env.TZ = 'Asia/Shanghai'
      expect(serverDateIso('2026-09-01T16:30:00')).toBe('2026-09-02')
    } finally {
      if (local === undefined) delete process.env.TZ
      else process.env.TZ = local
    }
  })
})

describe('serverTimeLabel', () => {
  it('formats the LOCAL wall-clock time of a naive UTC timestamp', () => {
    const local = process.env.TZ
    try {
      process.env.TZ = 'Asia/Shanghai'
      // UTC 16:30 → 北京次日 00:30
      expect(serverTimeLabel('2026-09-01T16:30:00')).toBe('00:30')
    } finally {
      if (local === undefined) delete process.env.TZ
      else process.env.TZ = local
    }
  })

  it('returns empty string for invalid input', () => {
    expect(serverTimeLabel('')).toBe('')
  })
})
