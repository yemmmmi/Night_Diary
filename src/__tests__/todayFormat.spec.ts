import { describe, expect, it } from 'vitest'

import { chineseDateLabel, todaySubtitle } from '@/shared/utils/todayFormat'

describe('chineseDateLabel', () => {
  it('formats a full chinese date for the big serif header', () => {
    expect(chineseDateLabel('2026-08-31')).toBe('八月三十一日')
  })

  it('formats single-digit month and day', () => {
    expect(chineseDateLabel('2026-01-05')).toBe('一月五日')
  })

  it('formats tens without a leading 一十', () => {
    expect(chineseDateLabel('2026-10-20')).toBe('十月二十日')
    expect(chineseDateLabel('2026-12-11')).toBe('十二月十一日')
  })

  it('returns empty string for invalid input', () => {
    expect(chineseDateLabel('not-a-date')).toBe('')
  })
})

describe('todaySubtitle', () => {
  it('joins year and weekday with a middle dot', () => {
    expect(todaySubtitle('2026-08-31')).toBe('2026 · 周一')
  })

  it('returns empty string for invalid input', () => {
    expect(todaySubtitle('')).toBe('')
  })
})
