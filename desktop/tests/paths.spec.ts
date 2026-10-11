import path from 'node:path'

import { describe, expect, it } from 'vitest'

import { resolveBackendPaths } from '../src/paths'

describe('resolveBackendPaths', () => {
  it('resolves bundled resources in packaged mode', () => {
    const out = resolveBackendPaths({
      packaged: true,
      resourcesPath: 'C:/App/resources',
      repoRoot: 'C:/repo',
    })
    expect(out.pythonExe).toBe(path.join('C:/App/resources', 'runtime', 'python.exe'))
    expect(out.serverDir).toBe(path.join('C:/App/resources', 'server'))
    expect(out.frontendDir).toBe(path.join('C:/App/resources', 'frontend'))
  })

  it('uses the repo layout in dev mode and honours a python override', () => {
    const out = resolveBackendPaths({
      packaged: false,
      resourcesPath: 'ignored',
      repoRoot: 'C:/repo',
      pythonOverride: 'C:/repo/server/.venv/Scripts/python.exe',
    })
    expect(out.pythonExe).toBe('C:/repo/server/.venv/Scripts/python.exe')
    expect(out.serverDir).toBe(path.join('C:/repo', 'server'))
    expect(out.frontendDir).toBe(path.join('C:/repo', 'dist'))
  })
})