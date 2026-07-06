import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { useDevStore } from '@/stores/dev'
import type { TraceSummary } from '@/shared/api/dev'

describe('dev store', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('initializes with null activeTraceId', () => {
    const store = useDevStore()
    expect(store.activeTraceId).toBeNull()
  })

  it('setActiveTrace sets trace id and persists to localStorage', () => {
    const store = useDevStore()
    store.setActiveTrace('test-trace-id')
    expect(store.activeTraceId).toBe('test-trace-id')
    expect(localStorage.getItem('night-diary-active-trace-id')).toBe('test-trace-id')
  })

  it('setActiveTrace(null) clears trace id and localStorage', () => {
    const store = useDevStore()
    store.setActiveTrace('test-trace-id')
    store.setActiveTrace(null)
    expect(store.activeTraceId).toBeNull()
    expect(localStorage.getItem('night-diary-active-trace-id')).toBeNull()
  })

  it('initializes with empty traceList', () => {
    const store = useDevStore()
    expect(store.traceList).toEqual([])
    expect(store.total).toBe(0)
  })

  it('initializes with null currentTraceDetail', () => {
    const store = useDevStore()
    expect(store.currentTraceDetail).toBeNull()
  })

  it('clearTraces resets traceList and currentTraceDetail', () => {
    const store = useDevStore()
    const fakeTrace: TraceSummary = {
      trace_id: '1',
      scenario: 'diary',
      status: 'completed',
      started_at: '',
      duration_ms: 100,
      span_count: 5,
      ref_id: null,
    }
    store.traceList = [fakeTrace]
    store.clearTraces()
    expect(store.traceList).toEqual([])
    expect(store.currentTraceDetail).toBeNull()
  })

  it('setActiveTrace can be called multiple times', () => {
    const store = useDevStore()
    store.setActiveTrace('trace-1')
    expect(store.activeTraceId).toBe('trace-1')
    store.setActiveTrace('trace-2')
    expect(store.activeTraceId).toBe('trace-2')
    expect(localStorage.getItem('night-diary-active-trace-id')).toBe('trace-2')
  })

  it('clearTraces does not affect activeTraceId', () => {
    const store = useDevStore()
    store.setActiveTrace('persistent-trace')
    store.clearTraces()
    expect(store.activeTraceId).toBe('persistent-trace')
    expect(localStorage.getItem('night-diary-active-trace-id')).toBe('persistent-trace')
  })
})
