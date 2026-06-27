import { describe, expect, it } from 'vitest'
import { MODEL_PRESETS, modelsCopy } from '@/shared/copy/models'

describe('model presets', () => {
  it('每项预设都有 key/name/baseUrl/defaultModel/suggestedTier', () => {
    for (const p of MODEL_PRESETS) {
      expect(p.key).toBeTruthy()
      expect(p.name).toBeTruthy()
      expect(typeof p.baseUrl).toBe('string')
      expect(typeof p.defaultModel).toBe('string')
      expect(['light', 'medium', 'heavy', 'default']).toContain(p.suggestedTier)
    }
  })

  it('非 custom 预设的 baseUrl 都是 https 开头', () => {
    for (const p of MODEL_PRESETS) {
      if (p.key === 'custom') continue
      expect(p.baseUrl.startsWith('https://')).toBe(true)
    }
  })

  it('custom 预设留空，允许手填', () => {
    const custom = MODEL_PRESETS.find((p) => p.key === 'custom')
    expect(custom?.baseUrl).toBe('')
    expect(custom?.defaultModel).toBe('')
  })

  it('key 全局唯一', () => {
    const keys = MODEL_PRESETS.map((p) => p.key)
    expect(new Set(keys).size).toBe(keys.length)
  })

  it('modelsCopy 含必要文案', () => {
    expect(modelsCopy.tab).toBe('模型')
    expect(modelsCopy.pageTitle).toBeTruthy()
    expect(modelsCopy.presetSectionHint).toBeTruthy()
  })

  it('预设数量至少 8 个（含 custom）', () => {
    expect(MODEL_PRESETS.length).toBeGreaterThanOrEqual(8)
  })
})
