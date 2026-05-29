import { invoke } from '@tauri-apps/api/core'
import { onMounted, ref, type Ref } from 'vue'

const DEFAULT_DEV_BASE_URL = 'http://127.0.0.1:8000'
const HEALTH_PATH = '/health'
const HEALTH_INTERVAL_MS = 200
const HEALTH_MAX_ATTEMPTS = 150

export interface BackendState {
  ready: Ref<boolean>
  loading: Ref<boolean>
  error: Ref<string | null>
  baseUrl: Ref<string>
  init: () => Promise<void>
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
  try {
    return await invoke<boolean>('check_backend_health')
  } catch {
    // Browser-only dev (vite without Tauri): fetch fallback
    try {
      const url = new URL(HEALTH_PATH, baseUrl).toString()
      const response = await fetch(url)
      return response.ok
    } catch {
      return false
    }
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
    await new Promise((resolve) => setTimeout(resolve, intervalMs))
  }

  throw new Error('Backend health check timed out')
}

export function useBackend(): BackendState {
  const ready = ref(false)
  const loading = ref(true)
  const error = ref<string | null>(null)
  const baseUrl = ref('')

  async function init(): Promise<void> {
    loading.value = true
    error.value = null
    ready.value = false

    try {
      const url = await resolveBackendBaseUrl()
      baseUrl.value = url
      await waitForBackendHealth(url)
      ready.value = true
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
    } finally {
      loading.value = false
    }
  }

  onMounted(() => {
    void init()
  })

  return { ready, loading, error, baseUrl, init }
}
