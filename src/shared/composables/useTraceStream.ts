import { ref, watch, onUnmounted, type Ref } from 'vue'

import type { TraceSpan } from '@/shared/api/dev'
import { resolveBackendBaseUrl } from '@/shared/composables/useBackend'

export interface TraceInfo {
  status: string
  duration_ms: number
  span_count: number
}

export function useTraceStream(traceId: Ref<string | null>) {
  const spans = ref<TraceSpan[]>([])
  const status = ref<'idle' | 'connecting' | 'streaming' | 'done' | 'error'>('idle')
  const traceInfo = ref<TraceInfo | null>(null)
  let eventSource: EventSource | null = null
  let retryTimer: ReturnType<typeof setTimeout> | null = null

  async function connect(id: string) {
    status.value = 'connecting'
    const baseURL = await resolveBackendBaseUrl()
    eventSource = new EventSource(`${baseURL}/api/v1/dev/traces/${id}/stream`)

    eventSource.addEventListener('span_complete', (e: MessageEvent) => {
      const { span } = JSON.parse(e.data) as { span: TraceSpan }
      const idx = spans.value.findIndex((s) => s.span_id === span.span_id)
      if (idx >= 0) spans.value[idx] = span
      else spans.value.push(span)
      status.value = 'streaming'
    })

    eventSource.addEventListener('trace_complete', (e: MessageEvent) => {
      const { trace } = JSON.parse(e.data) as { trace: TraceInfo }
      traceInfo.value = trace
      status.value = 'done'
      eventSource?.close()
    })

    eventSource.addEventListener('span_error', () => {
      status.value = 'error'
    })

    eventSource.onerror = () => {
      if (status.value === 'done') return
      if (status.value === 'connecting') {
        // 首次连接失败，3 秒后重试一次
        eventSource?.close()
        retryTimer = setTimeout(() => {
          if (traceId.value) connect(traceId.value)
        }, 3000)
      } else {
        status.value = 'error'
      }
    }
  }

  watch(
    traceId,
    (id) => {
      if (retryTimer) clearTimeout(retryTimer)
      if (eventSource) {
        eventSource.close()
        eventSource = null
      }
      spans.value = []
      traceInfo.value = null
      if (!id) {
        status.value = 'idle'
        return
      }
      connect(id)
    },
    { immediate: true },
  )

  onUnmounted(() => {
    if (retryTimer) clearTimeout(retryTimer)
    eventSource?.close()
  })

  return { spans, status, traceInfo }
}
