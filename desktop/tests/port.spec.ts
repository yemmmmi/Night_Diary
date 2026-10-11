import { describe, expect, it } from 'vitest'

import { findFreePort } from '../src/port'

describe('findFreePort', () => {
  it('returns a usable ephemeral port', async () => {
    const port = await findFreePort()
    expect(Number.isInteger(port)).toBe(true)
    expect(port).toBeGreaterThan(1024)
    expect(port).toBeLessThanOrEqual(65535)
  })
})