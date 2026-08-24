import { ref, onUnmounted, type Ref } from 'vue'
import { abortStreaming } from '@/shared/api/conversation'

const WATCHDOG_TIMEOUT_MS = 120_000 // 120s no-event → idle
const ABORT_CONFIRM_TIMEOUT_MS = 10_000 // 10s abort 确认超时

const REPLY_START_EVENT = 'reply_start'
const TEXT_DELTA_EVENT = 'text_delta'
const TEXT_END_EVENT = 'text_end'
const REPLY_END_EVENT = 'reply_end'
const RETRACT_EVENT = 'retract'
const PROTOCOL_BLOCK_EVENT = 'protocol_block'

export type StreamingReplyStatus = 'idle' | 'streaming' | 'done' | 'retracted'

export type StreamMode = 'daily' | 'followup' | 'introspection'

/**
 * RenderSegment
 *
 * P2 render model: a reply is now an ordered list of segments that mix
 * plain text with structured protocol blocks. Text deltas accumulate into
 * the `currentTextBuffer` and are flushed as a single `text` segment
 * whenever a protocol block arrives or the reply ends, so adjacent text
 * deltas never fragment into many tiny segments.
 */
export type RenderSegment =
  | { kind: 'text'; content: string }
  | {
      kind: 'protocol_block'
      blockType: string
      blockId: string
      data: Record<string, unknown>
      status: 'pending' | 'accepted' | 'rejected'
    }

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
  segments: Ref<RenderSegment[]>
  /** Latest mode announced via a ``mode_state`` protocol block (V3.x). */
  currentMode: Ref<StreamMode | null>
  /** One-time gentle notice trigger when the mode was auto-changed. */
  modeNotice: Ref<boolean>
  connect: (sseUrl: string) => void
  disconnect: () => void
  reset: () => void
  abort: (conversationId: string, traceId: string) => void
  acceptBlock: (blockId: string) => Promise<void>
  rejectBlock: (blockId: string) => void
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
  const segments = ref<RenderSegment[]>([])
  const currentMode = ref<StreamMode | null>(null)
  const modeNotice = ref(false)

  let eventSource: EventSource | null = null
  let pendingTokens = ''
  // segments model: text deltas accumulate here and are flushed as a single
  // `text` segment when a protocol block arrives or the reply ends. Unlike
  // pendingTokens (RAF-batched for render perf), this buffer is only flushed
  // at segment boundaries.
  let currentTextBuffer = ''
  let rafId: number | null = null
  let watchdogTimer: ReturnType<typeof setTimeout> | null = null
  let abortConfirmTimer: ReturnType<typeof setTimeout> | null = null

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
    segments.value = []
    currentTextBuffer = ''
    currentMode.value = null
    modeNotice.value = false
    status.value = 'streaming'

    eventSource = new EventSource(sseUrl)

    eventSource.addEventListener(REPLY_START_EVENT, () => {
      resetWatchdog()
    })

    eventSource.addEventListener(TEXT_DELTA_EVENT, (e: MessageEvent) => {
      try {
        const { text } = JSON.parse(e.data) as { text: string }
        pendingTokens += text
        // segments 模型用：累积到独立的文本 buffer，在协议块到达或
        // reply_end 时 flush 为一个 text segment。replyText 仍走原有的
        // pendingTokens + RAF flush 路径（向后兼容历史消息渲染）。
        currentTextBuffer += text
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
      // flush 剩余文本为最后一个 text segment
      if (currentTextBuffer) {
        segments.value = [
          ...segments.value,
          { kind: 'text', content: currentTextBuffer },
        ]
        currentTextBuffer = ''
      }
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
      if (abortConfirmTimer) {
        clearTimeout(abortConfirmTimer)
        abortConfirmTimer = null
      }
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

    eventSource.addEventListener(PROTOCOL_BLOCK_EVENT, (e: MessageEvent) => {
      try {
        const payload = JSON.parse(e.data) as {
          block: {
            block_type: string
            block_id: string
            data: Record<string, unknown>
          }
        }
        // ``mode_state`` is a state signal (header badge / one-time notice),
        // not a persistent chat bubble segment — handle it apart.
        if (payload.block.block_type === 'mode_state') {
          const mode = payload.block.data?.mode as StreamMode | undefined
          if (mode === 'daily' || mode === 'followup' || mode === 'introspection') {
            const changed = currentMode.value !== null && currentMode.value !== mode
            currentMode.value = mode
            // Show a gentle one-time notice only on an auto-change (dedup: the
            // backend sets light_notice=true only on the first auto switch).
            if (payload.block.data?.light_notice === true || changed) {
              modeNotice.value = true
            }
          }
          resetWatchdog()
          return
        }
        // 先 flush 文本 buffer 为一个 text segment
        if (currentTextBuffer) {
          segments.value = [
            ...segments.value,
            { kind: 'text', content: currentTextBuffer },
          ]
          currentTextBuffer = ''
        }
        // 再 push 协议块 segment
        segments.value = [
          ...segments.value,
          {
            kind: 'protocol_block',
            blockType: payload.block.block_type,
            blockId: payload.block.block_id,
            data: payload.block.data,
            status: 'pending',
          },
        ]
        resetWatchdog()
      } catch {
        // Malformed — ignore
      }
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

  function abort(conversationId: string, traceId: string): void {
    if (status.value !== 'streaming') return

    // 发送 abort 请求（fire-and-forget，响应不重要——10s 确认定时器兜底）
    abortStreaming(conversationId, traceId).catch(() => {
      // 网络错误忽略——10s 确认定时器会强制回 idle
    })

    // 启动 10s 确认定时器
    if (abortConfirmTimer) clearTimeout(abortConfirmTimer)
    abortConfirmTimer = setTimeout(() => {
      // 10s 内未收到 REPLY_END → 强制回 idle
      flushTokens()
      status.value = 'idle'
      abortConfirmTimer = null
    }, ABORT_CONFIRM_TIMEOUT_MS)
  }

  async function acceptBlock(blockId: string): Promise<void> {
    segments.value = segments.value.map((s) =>
      s.kind === 'protocol_block' && s.blockId === blockId
        ? { ...s, status: 'accepted' as const }
        : s,
    )
  }

  function rejectBlock(blockId: string): void {
    segments.value = segments.value.map((s) =>
      s.kind === 'protocol_block' && s.blockId === blockId
        ? { ...s, status: 'rejected' as const }
        : s,
    )
  }

  function disconnect(): void {
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
    cancelFlush()
    clearWatchdog()
    if (abortConfirmTimer) {
      clearTimeout(abortConfirmTimer)
      abortConfirmTimer = null
    }
    pendingTokens = ''
    currentTextBuffer = ''
  }

  function reset(): void {
    disconnect()
    replyText.value = ''
    status.value = 'idle'
    citations.value = []
    segments.value = []
    currentTextBuffer = ''
    currentMode.value = null
    modeNotice.value = false
  }

  onUnmounted(() => {
    disconnect()
  })

  return {
    replyText,
    status,
    citations,
    segments,
    currentMode,
    modeNotice,
    connect,
    disconnect,
    reset,
    abort,
    acceptBlock,
    rejectBlock,
  }
}
