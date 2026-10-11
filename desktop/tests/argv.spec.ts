import { describe, expect, it } from 'vitest'

import { parseBackendUrl } from '../src/argv'

describe('parseBackendUrl', () => {
  it('extracts the backend url from additionalArguments', () => {
    const argv = ['electron', '--backend-url=http://127.0.0.1:9123', '--other']
    expect(parseBackendUrl(argv)).toBe('http://127.0.0.1:9123')
  })

  it('returns undefined when absent', () => {
    expect(parseBackendUrl(['electron'])).toBeUndefined()
  })
})