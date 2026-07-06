import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { nextTick, ref } from 'vue'

// ── Mock EventSource ──────────────────────────────────────────────────
// The test environment (happy-dom) may not provide a real EventSource,
// so we create a mock that simulates SSE event dispatching.

class MockEventSource {
  static instances: MockEventSource[] = []
  url: string
  listeners: Record<string, ((e: MessageEvent) => void)[]> = {}
  onerror: (() => void) | null = null
  closed = false

  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }

  addEventListener(type: string, listener: (e: MessageEvent) => void): void {
    if (!this.listeners[type]) this.listeners[type] = []
    this.listeners[type].push(listener)
  }

  removeEventListener(type: string, listener: (e: MessageEvent) => void): void {
    if (this.listeners[type]) {
      this.listeners[type] = this.listeners[type].filter((l) => l !== listener)
    }
  }

  close(): void {
    this.closed = true
  }

  /** Simulate an SSE event being received. */
  simulateEvent(type: string, data: unknown): void {
    const event = new MessageEvent(type, { data: JSON.stringify(data) })
    this.listeners[type]?.forEach((l) => l(event))
  }
}

// Mock resolveBackendBaseUrl so connect() doesn't try a real network call.
vi.mock('@/shared/composables/useBackend', () => ({
  resolveBackendBaseUrl: vi.fn().mockResolvedValue('http://127.0.0.1:8000'),
}))

// Import after mocks are set up.
import { useTraceStream } from '@/shared/composables/useTraceStream'

describe('useTraceStream', () => {
  let warnSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    MockEventSource.instances = []
    vi.stubGlobal('EventSource', MockEventSource)
    setActivePinia(createPinia())
    // Suppress Vue's onUnmounted warning since composable is called
    // outside a component setup context in tests.
    warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('starts in idle status when traceId is null', () => {
    const traceId = ref<string | null>(null)
    const { status } = useTraceStream(traceId)
    expect(status.value).toBe('idle')
  })

  it('connects when traceId is set', async () => {
    const traceId = ref<string | null>('test-trace')
    const { status } = useTraceStream(traceId)
    // Wait for the async connect() to create the EventSource.
    await vi.waitFor(() => {
      expect(MockEventSource.instances.length).toBeGreaterThan(0)
    })
    expect(status.value).toBe('connecting')
  })

  it('receives span_complete events and transitions to streaming', async () => {
    const traceId = ref<string | null>('test-trace')
    const { spans, status } = useTraceStream(traceId)
    await vi.waitFor(() => {
      expect(MockEventSource.instances.length).toBeGreaterThan(0)
    })

    const es = MockEventSource.instances[0]
    es.simulateEvent('span_complete', {
      span: {
        span_id: 'span-1',
        stage_name: 'S1_test',
        stage_label: '测试',
        status: 'completed',
        duration_ms: 12.5,
        input_snapshot: {},
        output_snapshot: {},
        metadata: {},
        child_spans: [],
        error: null,
      },
    })

    expect(spans.value.length).toBe(1)
    expect(spans.value[0].stage_name).toBe('S1_test')
    expect(status.value).toBe('streaming')
  })

  it('updates existing span on duplicate span_complete', async () => {
    const traceId = ref<string | null>('test-trace')
    const { spans } = useTraceStream(traceId)
    await vi.waitFor(() => {
      expect(MockEventSource.instances.length).toBeGreaterThan(0)
    })

    const es = MockEventSource.instances[0]
    const spanData = {
      span: {
        span_id: 'span-1',
        stage_name: 'S1_test',
        stage_label: '测试',
        status: 'completed',
        duration_ms: 12.5,
        input_snapshot: {},
        output_snapshot: {},
        metadata: {},
        child_spans: [],
        error: null,
      },
    }
    es.simulateEvent('span_complete', spanData)
    expect(spans.value.length).toBe(1)

    // Send same span_id again with updated duration
    es.simulateEvent('span_complete', {
      span: {
        ...spanData.span,
        duration_ms: 99.9,
      },
    })
    expect(spans.value.length).toBe(1)
    expect(spans.value[0].duration_ms).toBe(99.9)
  })

  it('closes EventSource and sets done status on trace_complete', async () => {
    const traceId = ref<string | null>('test-trace')
    const { status, traceInfo } = useTraceStream(traceId)
    await vi.waitFor(() => {
      expect(MockEventSource.instances.length).toBeGreaterThan(0)
    })

    const es = MockEventSource.instances[0]
    es.simulateEvent('trace_complete', {
      trace: { status: 'completed', duration_ms: 500, span_count: 5 },
    })

    expect(status.value).toBe('done')
    expect(traceInfo.value).toEqual({
      status: 'completed',
      duration_ms: 500,
      span_count: 5,
    })
    expect(es.closed).toBe(true)
  })

  it('sets error status on span_error event', async () => {
    const traceId = ref<string | null>('test-trace')
    const { status } = useTraceStream(traceId)
    await vi.waitFor(() => {
      expect(MockEventSource.instances.length).toBeGreaterThan(0)
    })

    const es = MockEventSource.instances[0]
    es.simulateEvent('span_error', {})
    expect(status.value).toBe('error')
  })

  it('clears spans when traceId becomes null', async () => {
    const traceId = ref<string | null>('test-trace')
    const { spans } = useTraceStream(traceId)
    await vi.waitFor(() => {
      expect(MockEventSource.instances.length).toBeGreaterThan(0)
    })

    const es = MockEventSource.instances[0]
    es.simulateEvent('span_complete', {
      span: {
        span_id: 'span-1',
        stage_name: 'S1_test',
        stage_label: '测试',
        status: 'completed',
        duration_ms: 12.5,
        input_snapshot: {},
        output_snapshot: {},
        metadata: {},
        child_spans: [],
        error: null,
      },
    })
    expect(spans.value.length).toBe(1)

    // Setting traceId to null should clear spans and reset to idle.
    // Vue's watch is async (flush: 'pre'), so we need to wait for nextTick.
    traceId.value = null
    await nextTick()
    expect(spans.value.length).toBe(0)
  })
})
