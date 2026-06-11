import { invoke } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'
import { onMounted, onUnmounted, ref, type Ref } from 'vue'

const DEFAULT_DEV_BASE_URL = 'http://127.0.0.1:8000'
const HEALTH_PATH = '/health'
const HEALTH_INTERVAL_MS = 150
const HEALTH_MAX_ATTEMPTS = 150
const TAURI_POLL_INTERVAL_MS = 100
const BOOTSTRAP_POLL_INTERVAL_MS = 150
const BOOTSTRAP_MAX_WAIT_MS = 60_000
const READY_PATH = '/ready'

export interface BackendState {
  ready: Ref<boolean>
  bootstrapReady: Ref<boolean>
  loading: Ref<boolean>
  error: Ref<string | null>
  baseUrl: Ref<string>
  startupProgress: Ref<number | null>
  init: () => Promise<void>
}

let bootstrapReadyFlag = false
let bootstrapWaitPromise: Promise<void> | null = null
let bootstrapUnlisten: (() => void) | undefined

export function isBootstrapReady(): boolean {
  return bootstrapReadyFlag
}

export function resetBootstrapReady(): void {
  bootstrapReadyFlag = false
  bootstrapWaitPromise = null
  bootstrapUnlisten?.()
  bootstrapUnlisten = undefined
}

async function isTauriBootstrapReady(): Promise<boolean> {
  try {
    return await invoke<boolean>('is_bootstrap_ready')
  } catch {
    return false
  }
}

async function probeBootstrapReady(baseUrl: string): Promise<boolean> {
  if (isTauriRuntime()) {
    if (await isTauriBootstrapReady()) {
      return true
    }
    try {
      return await invoke<boolean>('check_backend_bootstrap')
    } catch {
      return false
    }
  }

  try {
    const url = new URL(READY_PATH, baseUrl).toString()
    const response = await fetch(url)
    return response.ok
  } catch {
    return false
  }
}

function markBootstrapReady(): void {
  bootstrapReadyFlag = true
}

/** Wait until ServiceContainer bootstrap completes (API-safe). */
export async function waitForBootstrapReady(
  baseUrl?: string,
  maxWaitMs: number = BOOTSTRAP_MAX_WAIT_MS,
): Promise<void> {
  if (bootstrapReadyFlag) {
    return
  }

  if (!bootstrapWaitPromise) {
    bootstrapWaitPromise = createBootstrapWait(baseUrl, maxWaitMs)
  }

  return bootstrapWaitPromise
}

async function createBootstrapWait(
  baseUrl?: string,
  maxWaitMs: number = BOOTSTRAP_MAX_WAIT_MS,
): Promise<void> {
  const url = baseUrl ?? (await resolveBackendBaseUrl())

  if (await probeBootstrapReady(url)) {
    markBootstrapReady()
    return
  }

  return new Promise((resolve, reject) => {
    let settled = false
    let pollTimer: ReturnType<typeof setInterval> | undefined

    const cleanup = () => {
      if (pollTimer) clearInterval(pollTimer)
    }

    const finish = () => {
      if (settled) return
      settled = true
      clearTimeout(timeout)
      cleanup()
      markBootstrapReady()
      resolve()
    }

    const fail = (message: string) => {
      if (settled) return
      settled = true
      clearTimeout(timeout)
      cleanup()
      reject(new Error(message))
    }

    const timeout = setTimeout(
      () => fail('AI 引擎初始化超时'),
      maxWaitMs,
    )

    void (async () => {
      if (isTauriRuntime()) {
        try {
          bootstrapUnlisten?.()
          bootstrapUnlisten = await listen<number>('backend-bootstrap-ready', () => {
            finish()
          })
        } catch {
          // fall back to polling
        }
      }

      pollTimer = setInterval(() => {
        void probeBootstrapReady(url).then((ready) => {
          if (ready) finish()
        })
      }, BOOTSTRAP_POLL_INTERVAL_MS)
    })()
  })
}

function startBootstrapWatch(baseUrl: string): void {
  void waitForBootstrapReady(baseUrl)
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

async function isTauriBackendReady(): Promise<boolean> {
  try {
    return await invoke<boolean>('is_backend_ready')
  } catch {
    return false
  }
}

async function probeBackendHealth(baseUrl: string): Promise<boolean> {
  if (isTauriRuntime()) {
    if (await isTauriBackendReady()) {
      return true
    }
    try {
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

/** Tauri: prefer Rust `backend-ready` event + is_backend_ready flag (no redundant HTTP polling). */
async function waitForTauriBackend(maxWaitMs = 30_000): Promise<void> {
  if (await isTauriBackendReady()) {
    return
  }

  return new Promise((resolve, reject) => {
    let settled = false
    let unlistenReady: (() => void) | undefined
    let pollTimer: ReturnType<typeof setInterval> | undefined

    const cleanup = () => {
      unlistenReady?.()
      if (pollTimer) clearInterval(pollTimer)
    }

    const finish = () => {
      if (settled) return
      settled = true
      clearTimeout(timeout)
      cleanup()
      resolve()
    }

    const fail = (message: string) => {
      if (settled) return
      settled = true
      clearTimeout(timeout)
      cleanup()
      reject(new Error(message))
    }

    const timeout = setTimeout(
      () => fail('Backend health check timed out'),
      maxWaitMs,
    )

    void (async () => {
      try {
        unlistenReady = await listen<number>('backend-ready', () => {
          clearTimeout(timeout)
          finish()
        })
      } catch {
        // event API unavailable — fall back to polling only
      }

      pollTimer = setInterval(() => {
        void isTauriBackendReady().then((ready) => {
          if (ready) finish()
        })
      }, TAURI_POLL_INTERVAL_MS)
    })()
  })
}

export async function waitForBackendHealth(
  baseUrl: string,
  maxAttempts: number = HEALTH_MAX_ATTEMPTS,
  intervalMs: number = HEALTH_INTERVAL_MS,
): Promise<void> {
  if (isTauriRuntime()) {
    await waitForTauriBackend(maxAttempts * intervalMs)
    return
  }

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
  const bootstrapReady = ref(false)
  const loading = ref(true)
  const error = ref<string | null>(null)
  const baseUrl = ref('')
  const startupProgress = ref<number | null>(null)

  let unlistenProgress: (() => void) | undefined
  let unlistenBootstrap: (() => void) | undefined

  async function init(): Promise<void> {
    loading.value = true
    error.value = null
    ready.value = false
    bootstrapReady.value = false
    startupProgress.value = null
    resetBootstrapReady()

    if (isTauriRuntime()) {
      try {
        unlistenProgress?.()
        unlistenProgress = await listen<number>('backend-startup-progress', (event) => {
          startupProgress.value = event.payload
        })
        unlistenBootstrap?.()
        unlistenBootstrap = await listen<number>('backend-bootstrap-ready', () => {
          bootstrapReady.value = true
          markBootstrapReady()
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
      startBootstrapWatch(url)
      if (isBootstrapReady()) {
        bootstrapReady.value = true
      } else {
        void waitForBootstrapReady(url).then(() => {
          bootstrapReady.value = true
        })
      }
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
    unlistenBootstrap?.()
  })

  return { ready, bootstrapReady, loading, error, baseUrl, startupProgress, init }
}
