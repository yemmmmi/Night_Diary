import { invoke } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'
import { onMounted, onUnmounted, ref, type Ref } from 'vue'

const DEFAULT_DEV_BASE_URL = 'http://127.0.0.1:8000'
const HEALTH_PATH = '/health'
const HEALTH_INTERVAL_MS = 150
const HEALTH_MAX_ATTEMPTS = 150

export interface BackendState {
  ready: Ref<boolean>
  loading: Ref<boolean>
  error: Ref<string | null>
  baseUrl: Ref<string>
  startupProgress: Ref<number | null>
  init: () => Promise<void>
}

function isTauriRuntime(): boolean {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

export async function resolveBackendBaseUrl(): Promise<string> {
  try {
    const port = await invoke<number>('get_backend_port')
    return `http://127.0.0.1:${port}`
  } catch {
    return import.meta.env.VITE_API_BASE_URL ?? DEFAULT_DEV_BASE_URL
  }
}

async function probeBackendHealth(baseUrl: string): Promise<boolean> {
  if (isTauriRuntime()) {
    try {
      if (await invoke<boolean>('is_backend_ready')) {
        return true
      }
      return await invoke<boolean>('check_backend_health')
    } catch {
      return false
    }
  }

  try {
    const url = new URL(HEALTH_PATH, baseUrl).toString()
    const response = await fetch(url)
    return response.ok
  } catch {
    return false
  }
}

export async function waitForBackendHealth(
  baseUrl: string,
  maxAttempts: number = HEALTH_MAX_ATTEMPTS,
  intervalMs: number = HEALTH_INTERVAL_MS,
): Promise<void> {
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    if (await probeBackendHealth(baseUrl)) {
      return
    }
    await sleep(intervalMs)
  }

  throw new Error('Backend health check timed out')
}

export function useBackend(): BackendState {
  const ready = ref(false)
  const loading = ref(true)
  const error = ref<string | null>(null)
  const baseUrl = ref('')
  const startupProgress = ref<number | null>(null)

  let unlistenProgress: (() => void) | undefined

  async function init(): Promise<void> {
    loading.value = true
    error.value = null
    ready.value = false
    startupProgress.value = null

    if (isTauriRuntime()) {
      try {
        unlistenProgress?.()
        unlistenProgress = await listen<number>('backend-startup-progress', (event) => {
          startupProgress.value = event.payload
        })
      } catch {
        // ignore if event API unavailable
      }
    }

    try {
      const url = await resolveBackendBaseUrl()
      baseUrl.value = url
      await waitForBackendHealth(url)
      ready.value = true
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
    } finally {
      loading.value = false
      startupProgress.value = null
    }
  }

  onMounted(() => {
    void init()
  })

  onUnmounted(() => {
    unlistenProgress?.()
  })

  return { ready, loading, error, baseUrl, startupProgress, init }
}
