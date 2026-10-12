import path from 'node:path'

import { describe, expect, it, vi } from 'vitest'

import { resolveDataDir } from '../src/dataDir'

const inputs = {
  resourcesPath: 'D:/NightDiary/resources',
  appData: 'C:/Users/u/AppData/Roaming',
}

describe('resolveDataDir', () => {
  it('uses a portable data dir next to the install root when packaged', () => {
    const migrate = vi.fn()
    const out = resolveDataDir({
      ...inputs,
      packaged: true,
      existsSync: () => false,
      migrate,
    })
    expect(out).toBe(path.join('D:/NightDiary', 'data'))
    expect(migrate).not.toHaveBeenCalled()
  })

  it('migrates the legacy AppData dir once on first portable run', () => {
    const migrate = vi.fn()
    const legacy = path.join(inputs.appData, 'night-diary')
    const portable = path.join('D:/NightDiary', 'data')
    const out = resolveDataDir({
      ...inputs,
      packaged: true,
      existsSync: (p) => p === legacy,
      readdirSync: (p) => (p === legacy ? ['night_diary.db'] : []),
      migrate,
    })
    expect(out).toBe(portable)
    expect(migrate).toHaveBeenCalledWith(legacy, portable)
  })

  it('does not migrate an empty legacy dir', () => {
    const legacy = path.join(inputs.appData, 'night-diary')
    const migrate = vi.fn()
    const out = resolveDataDir({
      ...inputs,
      packaged: true,
      existsSync: (p) => p === legacy,
      readdirSync: () => [],
      migrate,
    })
    expect(out).toBe(path.join('D:/NightDiary', 'data'))
    expect(migrate).not.toHaveBeenCalled()
  })

  it('does not migrate again once the portable dir exists', () => {
    const portable = path.join('D:/NightDiary', 'data')
    const migrate = vi.fn()
    const out = resolveDataDir({
      ...inputs,
      packaged: true,
      existsSync: (p) => p === portable || p === path.join(inputs.appData, 'night-diary'),
      migrate,
    })
    expect(out).toBe(portable)
    expect(migrate).not.toHaveBeenCalled()
  })

  it('keeps %APPDATA% in dev mode', () => {
    const migrate = vi.fn()
    const out = resolveDataDir({
      ...inputs,
      packaged: false,
      existsSync: () => true,
      migrate,
    })
    expect(out).toBe(path.join(inputs.appData, 'night-diary'))
    expect(migrate).not.toHaveBeenCalled()
  })
})
