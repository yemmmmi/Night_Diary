import { onUnmounted, ref } from 'vue'

import {
  getModelDownloadStatus,
  startModelDownload,
  type ModelDownloadStatus,
} from '@/shared/api/modelDownload'

const POLL_INTERVAL_MS = 800

export function useModelDownload() {
  const status = ref<ModelDownloadStatus | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  let pollTimer: ReturnType<typeof setInterval> | undefined

  function stopPolling() {
    if (pollTimer !== undefined) {
      clearInterval(pollTimer)
      pollTimer = undefined
    }
  }

  async function refresh() {
    status.value = await getModelDownloadStatus()
    return status.value
  }

  async function ensureModels() {
    loading.value = true
    error.value = null
    stopPolling()

    try {
      let snap = await refresh()
      if (snap.all_ready) {
        return snap
      }

      await startModelDownload()
      snap = await refresh()

      await new Promise<void>((resolve, reject) => {
        pollTimer = setInterval(() => {
          void refresh()
            .then((next) => {
              if (next.all_ready) {
                stopPolling()
                resolve()
                return
              }
              const failed = next.items.find((item) => item.status === 'error')
              if (failed?.error) {
                stopPolling()
                reject(new Error(failed.error))
              }
            })
            .catch((err: unknown) => {
              stopPolling()
              reject(err instanceof Error ? err : new Error(String(err)))
            })
        }, POLL_INTERVAL_MS)
      })

      return await refresh()
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  onUnmounted(stopPolling)

  return { status, loading, error, refresh, ensureModels, stopPolling }
}
