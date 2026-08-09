import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

// ── Mock EventSource ──────────────────────────────────────────────────
// The test environment (happy-dom) does not provide a native EventSource,
// so we create a mock that simulates SSE event dispatching. The shape
// mirrors the one in useTraceStream.spec.ts to keep test conventions
// consistent across the codebase.

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

import { useStreamingReply } from '@/shared/composables/useStreamingReply'

describe('useStreamingReply', () => {
  let warnSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    MockEventSource.instances = []
    vi.useFakeTimers()
    vi.stubGlobal('EventSource', MockEventSource)
    // Suppress Vue's onUnmounted warning since the composable is called
    // outside of a component setup context in these unit tests.
    warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    warnSpy.mockRestore()
  })

  it('starts in idle status with empty text', () => {
    const { status, replyText } = useStreamingReply()
    expect(status.value).toBe('idle')
    expect(replyText.value).toBe('')
  })

  it('accumulates TEXT_DELTA events via RAF batching', async () => {
    const { replyText, connect } = useStreamingReply()
    connect('http://localhost/sse')

    const mockES = MockEventSource.instances[0]
    mockES.simulateEvent('text_delta', { text: 'Hello' })
    mockES.simulateEvent('text_delta', { text: ' ' })
    mockES.simulateEvent('text_delta', { text: 'world' })

    // Flush RAF + timers
    await vi.runAllTimersAsync()
    await nextTick()

    expect(replyText.value).toBe('Hello world')
  })

  it('replaces replyText on RETRACT event', async () => {
    const { replyText, status, connect } = useStreamingReply()
    connect('http://localhost/sse')

    const mockES = MockEventSource.instances[0]
    mockES.simulateEvent('text_delta', { text: '部分内容' })
    await vi.runAllTimersAsync()

    mockES.simulateEvent('retract', { reason: 'crisis', replacement: '安全模板' })
    await vi.runAllTimersAsync()

    expect(replyText.value).toBe('安全模板')
    expect(status.value).toBe('retracted')
  })

  it('transitions to done on REPLY_END', async () => {
    const { status, connect } = useStreamingReply()
    connect('http://localhost/sse')

    const mockES = MockEventSource.instances[0]
    mockES.simulateEvent('reply_end', { citations: [], usage: {} })
    await vi.runAllTimersAsync()

    expect(status.value).toBe('done')
  })

  it('watchdog resets to idle after 120s without events', async () => {
    const { status, connect } = useStreamingReply()
    connect('http://localhost/sse')

    const mockES = MockEventSource.instances[0]
    mockES.simulateEvent('reply_start', { intent: 'casual_chat' })
    await nextTick()

    vi.advanceTimersByTime(121_000)
    await nextTick()

    expect(status.value).toBe('idle')
  })

  it('citation data is stored from REPLY_END', async () => {
    const { citations, connect } = useStreamingReply()
    connect('http://localhost/sse')

    const mockES = MockEventSource.instances[0]
    const testCitations = [{ source_type: 'diary', source_name: 'test' }]
    mockES.simulateEvent('reply_end', {
      citations: testCitations,
      usage: { tokens_in: 50 },
    })
    await vi.runAllTimersAsync()

    expect(citations.value).toEqual(testCitations)
  })
})
