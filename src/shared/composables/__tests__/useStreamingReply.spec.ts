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

describe('useStreamingReply protocol block segments', () => {
  beforeEach(() => {
    MockEventSource.instances = []
    vi.useFakeTimers()
    vi.stubGlobal('EventSource', MockEventSource)
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('accumulates protocol_block as separate segment from text', async () => {
    const { segments, connect } = useStreamingReply()
    connect('http://localhost/sse')

    const mockES = MockEventSource.instances[0]
    mockES.simulateEvent('text_delta', { text: '你好，' })
    mockES.simulateEvent('text_delta', { text: '我有个建议：' })
    await vi.runAllTimersAsync()

    mockES.simulateEvent('protocol_block', {
      type: 'protocol_block',
      trace_id: 'test',
      block: {
        block_type: 'plan_proposal',
        block_id: 'p1',
        data: { title: '早睡计划', tasks: [] },
      },
    })
    await vi.runAllTimersAsync()

    // 应该有 2 个段：1 个文本段 + 1 个协议块段
    expect(segments.value.length).toBe(2)
    expect(segments.value[0].kind).toBe('text')
    expect((segments.value[0] as { content: string }).content).toContain('你好')
    expect(segments.value[1].kind).toBe('protocol_block')
    expect(
      (segments.value[1] as { blockType: string }).blockType,
    ).toBe('plan_proposal')
  })

  it('protocol_block segment has pending status initially', async () => {
    const { segments, connect } = useStreamingReply()
    connect('http://localhost/sse')

    const mockES = MockEventSource.instances[0]
    mockES.simulateEvent('protocol_block', {
      type: 'protocol_block',
      trace_id: 'test',
      block: {
        block_type: 'plan_proposal',
        block_id: 'p1',
        data: { title: '测试', tasks: [] },
      },
    })
    await vi.runAllTimersAsync()

    expect(segments.value.length).toBe(1)
    expect(segments.value[0].kind).toBe('protocol_block')
    if (segments.value[0].kind === 'protocol_block') {
      expect(segments.value[0].status).toBe('pending')
    }
  })

  it('acceptBlock updates segment status to accepted', async () => {
    const { segments, connect, acceptBlock } = useStreamingReply()
    connect('http://localhost/sse')

    const mockES = MockEventSource.instances[0]
    mockES.simulateEvent('protocol_block', {
      type: 'protocol_block',
      trace_id: 'test',
      block: {
        block_type: 'plan_proposal',
        block_id: 'p1',
        data: { title: '测试', tasks: [] },
      },
    })
    await vi.runAllTimersAsync()

    await acceptBlock('p1')
    if (segments.value[0].kind === 'protocol_block') {
      expect(segments.value[0].status).toBe('accepted')
    }
  })

  it('rejectBlock updates segment status to rejected', async () => {
    const { segments, connect, rejectBlock } = useStreamingReply()
    connect('http://localhost/sse')

    const mockES = MockEventSource.instances[0]
    mockES.simulateEvent('protocol_block', {
      type: 'protocol_block',
      trace_id: 'test',
      block: {
        block_type: 'plan_proposal',
        block_id: 'p1',
        data: { title: '测试', tasks: [] },
      },
    })
    await vi.runAllTimersAsync()

    rejectBlock('p1')
    if (segments.value[0].kind === 'protocol_block') {
      expect(segments.value[0].status).toBe('rejected')
    }
  })

  it('replyText still works for backward compat', async () => {
    const { replyText, connect } = useStreamingReply()
    connect('http://localhost/sse')

    const mockES = MockEventSource.instances[0]
    mockES.simulateEvent('text_delta', { text: '纯文本回复' })
    await vi.runAllTimersAsync()

    // replyText 仍然累积纯文本（向后兼容历史消息渲染）
    expect(replyText.value).toBe('纯文本回复')
  })

  it('text after protocol_block creates new text segment', async () => {
    const { segments, connect } = useStreamingReply()
    connect('http://localhost/sse')

    const mockES = MockEventSource.instances[0]
    mockES.simulateEvent('text_delta', { text: '前文' })
    await vi.runAllTimersAsync()

    mockES.simulateEvent('protocol_block', {
      type: 'protocol_block',
      trace_id: 'test',
      block: {
        block_type: 'plan_proposal',
        block_id: 'p1',
        data: {},
      },
    })
    await vi.runAllTimersAsync()

    mockES.simulateEvent('text_delta', { text: '后文' })
    await vi.runAllTimersAsync()

    mockES.simulateEvent('reply_end', {})
    await vi.runAllTimersAsync()

    // 3 段：text + protocol_block + text
    expect(segments.value.length).toBe(3)
    expect(segments.value[0].kind).toBe('text')
    expect(segments.value[1].kind).toBe('protocol_block')
    expect(segments.value[2].kind).toBe('text')
  })
})
