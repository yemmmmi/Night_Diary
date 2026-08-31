import { describe, expect, it } from 'vitest'

import { buildDiaryMarkdown, diaryExportFilename } from '@/shared/utils/markdownExport'

describe('buildDiaryMarkdown', () => {
  it('renders date heading, body and emotion line', () => {
    const md = buildDiaryMarkdown({
      date: '2026-08-31',
      content: '今天去了江边。\n风很大。',
      emotions: ['平静', '期待'],
    })
    expect(md).toContain('# 2026-08-31')
    expect(md).toContain('今天去了江边。\n风很大。')
    expect(md).toContain('情绪：平静、期待')
  })

  it('omits the emotion line when no emotions', () => {
    const md = buildDiaryMarkdown({ date: '2026-08-31', content: '空白的一天。', emotions: [] })
    expect(md).not.toContain('情绪：')
    expect(md).toContain('空白的一天。')
  })
})

describe('diaryExportFilename', () => {
  it('uses the diary date as filename', () => {
    expect(diaryExportFilename('2026-08-31')).toBe('2026-08-31.md')
  })
})
