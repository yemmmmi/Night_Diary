/**
 * useMiddlewareStatus — polls /api/v1/dev/middleware-status and exposes the
 * degradation state (robustness P1-5).
 *
 * The banner is surfaced only in developer mode; end users are never shown
 * infrastructure internals. Polling is lazy: starts on first call of
 * start() and stops on dispose.
 */
import { onUnmounted, ref } from 'vue'

import { getMiddlewareStatus, type MiddlewareStatus } from '@/shared/api/dev'

const POLL_INTERVAL_MS = 60_000

export interface MiddlewareStatusState {
  status: Readonly<MiddlewareStatus> | null
  degraded: boolean
  loading: boolean
}

export function useMiddlewareStatus(): {
  status: ReturnType<typeof ref<MiddlewareStatus | null>>
  degraded: ReturnType<typeof ref<boolean>>
  start: () => void
} {
  const status = ref<MiddlewareStatus | null>(null)
  const degraded = ref(false)
  let timer: ReturnType<typeof setInterval> | null = null
  let started = false

  async function poll(): Promise<void> {
    try {
      const data = await getMiddlewareStatus()
      status.value = data
      degraded.value = Boolean(data.degraded)
    } catch {
      // Backend unreachable — keep the last known state; do not spam errors.
    }
  }

  function start(): void {
    if (started) return
    started = true
    void poll()
    timer = setInterval(() => void poll(), POLL_INTERVAL_MS)
  }

  onUnmounted(() => {
    if (timer) clearInterval(timer)
    timer = null
  })

  return { status, degraded, start }
}
