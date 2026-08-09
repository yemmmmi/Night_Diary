import { ref, onUnmounted, type Ref } from 'vue'

const WATCHDOG_TIMEOUT_MS = 120_000 // 120s no-event → idle

const REPLY_START_EVENT = 'reply_start'
const TEXT_DELTA_EVENT = 'text_delta'
const TEXT_END_EVENT = 'text_end'
const REPLY_END_EVENT = 'reply_end'
const RETRACT_EVENT = 'retract'

export type StreamingReplyStatus = 'idle' | 'streaming' | 'done' | 'retracted'

export interface ReplyEndPayload {
  citations?: Array<Record<string, unknown>>
  usage?: Record<string, number>
  error?: string
}

export interface RetractPayload {
  reason?: string
  replacement?: string
}

export interface StreamingReplyReturn {
  replyText: Ref<string>
  status: Ref<StreamingReplyStatus>
  citations: Ref<Array<Record<string, unknown>>>
  connect: (sseUrl: string) => void
  disconnect: () => void
  reset: () => void
}

/**
 * useStreamingReply
 *
 * Core frontend logic for consuming an SSE streaming reply. The caller is
 * responsible for building the full SSE URL (including auth / conversation
 * id query params) and passing it to `connect()` — this composable never
 * hardcodes a backend URL.
 *
 * Three key mechanisms:
 *
 * 1. RAF batching — high-frequency `text_delta` events are accumulated into
 *    `pendingTokens` and flushed once per animation frame, so we never
 *    trigger more than one reactive render per frame no matter how many
 *    tokens arrive.
 *
 * 2. 120s watchdog — every received event resets the timer; if no event
 *    arrives for 120s while in `streaming` state, we force-flush pending
 *    tokens and fall back to `idle` so the UI can never get stuck forever.
 *
 * 3. RETRACT replacement — on a `retract` event (crisis-safety) the entire
 *    `replyText` is *replaced* with the provided template rather than
 *    appended, and `status` moves to `retracted`.
 */
export function useStreamingReply(): StreamingReplyReturn {
  const replyText = ref('')
  const status = ref<StreamingReplyStatus>('idle')
  const citations = ref<Array<Record<string, unknown>>>([])

  let eventSource: EventSource | null = null
  let pendingTokens = ''
  let rafId: number | null = null
  let watchdogTimer: ReturnType<typeof setTimeout> | null = null

  function flushTokens(): void {
    if (pendingTokens) {
      replyText.value += pendingTokens
      pendingTokens = ''
    }
    rafId = null
  }

  function scheduleFlush(): void {
    if (rafId === null) {
      rafId = requestAnimationFrame(flushTokens)
    }
  }

  function cancelFlush(): void {
    if (rafId !== null) {
      cancelAnimationFrame(rafId)
      rafId = null
    }
  }

  function resetWatchdog(): void {
    if (watchdogTimer) clearTimeout(watchdogTimer)
    watchdogTimer = setTimeout(() => {
      // 120s without events → force flush + back to idle so the UI can
      // never remain stuck in `streaming` forever.
      if (status.value === 'streaming') {
        flushTokens()
        status.value = 'idle'
      }
    }, WATCHDOG_TIMEOUT_MS)
  }

  function clearWatchdog(): void {
    if (watchdogTimer) {
      clearTimeout(watchdogTimer)
      watchdogTimer = null
    }
  }

  function connect(sseUrl: string): void {
    // Tear down any previous session before starting a fresh one.
    disconnect()

    replyText.value = ''
    pendingTokens = ''
    citations.value = []
    status.value = 'streaming'

    eventSource = new EventSource(sseUrl)

    eventSource.addEventListener(REPLY_START_EVENT, () => {
      resetWatchdog()
    })

    eventSource.addEventListener(TEXT_DELTA_EVENT, (e: MessageEvent) => {
      try {
        const { text } = JSON.parse(e.data) as { text: string }
        pendingTokens += text
        scheduleFlush()
        resetWatchdog()
      } catch {
        // Malformed event data — ignore this delta but keep streaming.
      }
    })

    eventSource.addEventListener(TEXT_END_EVENT, () => {
      flushTokens()
      resetWatchdog()
    })

    eventSource.addEventListener(REPLY_END_EVENT, (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as ReplyEndPayload
        flushTokens()
        citations.value = data.citations || []
      } catch {
        // Even on parse error we must exit the streaming state.
        flushTokens()
      }
      status.value = 'done'
      clearWatchdog()
      eventSource?.close()
      eventSource = null
    })

    eventSource.addEventListener(RETRACT_EVENT, (e: MessageEvent) => {
      try {
        const { replacement } = JSON.parse(e.data) as RetractPayload
        // RETRACT *replaces* the entire replyText (crisis safety), it does
        // NOT append. Drop any pending tokens so they can't leak in later.
        pendingTokens = ''
        cancelFlush()
        replyText.value = replacement ?? ''
      } catch {
        // On parse error, still drop pending tokens and mark as retracted.
        pendingTokens = ''
        cancelFlush()
      }
      status.value = 'retracted'
      clearWatchdog()
    })

    eventSource.onerror = () => {
      if (status.value === 'streaming') {
        flushTokens()
        status.value = 'done'
      }
      clearWatchdog()
    }

    resetWatchdog()
  }

  function disconnect(): void {
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
    cancelFlush()
    clearWatchdog()
    pendingTokens = ''
  }

  function reset(): void {
    disconnect()
    replyText.value = ''
    status.value = 'idle'
    citations.value = []
  }

  onUnmounted(() => {
    disconnect()
  })

  return {
    replyText,
    status,
    citations,
    connect,
    disconnect,
    reset,
  }
}
