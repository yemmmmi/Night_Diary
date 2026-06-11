import { invoke } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'
import { onMounted, onUnmounted, ref, type Ref } from 'vue'

const DEFAULT_DEV_BASE_URL = 'http://127.0.0.1:8000'
const HEALTH_PATH = '/health'
const READY_PATH = '/ready'
const HEALTH_INTERVAL_MS = 150
const HEALTH_MAX_ATTEMPTS = 150
const TAURI_POLL_INTERVAL_MS = 100
const BOOTSTRAP_POLL_INTERVAL_MS = 150
const BOOTSTRAP_MAX_WAIT_MS = 60_000

export interface BackendState {
  ready: Ref<boolean>
  coreReady: Ref<boolean>
  loading: Ref<boolean>
  error: Ref<string | null>
  baseUrl: Ref<string>
  startupProgress: Ref<number | null>
  init: () => Promise<void>
}

let coreReadyFlag = false
let coreWaitPromise: Promise<void> | null = null

export function isCoreReady(): boolean {
  return coreReadyFlag
}

export function resetCoreReady(): void {
  coreReadyFlag = false
  coreWaitPromise = null
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

async function isTauriCoreReady(): Promise<boolean> {
  try {
    return await invoke<boolean>('is_core_ready')
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

async function probeCoreReady(baseUrl: string): Promise<boolean> {
  if (isTauriRuntime()) {
    if (await isTauriCoreReady()) {
      return true
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

/** Tauri: listen for `backend-ready` instead of redundant HTTP health polling. */
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
        unlistenReady = await listen<number>('backend-ready', () => finish())
      } catch {
        // fall back to polling
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

function markCoreReady(): void {
  coreReadyFlag = true
}

/** Wait until core bootstrap completes (`/ready` OK — diary CRUD safe). */
export async function waitForCoreReady(
  baseUrl?: string,
  maxWaitMs: number = BOOTSTRAP_MAX_WAIT_MS,
): Promise<void> {
  if (coreReadyFlag) {
    return
  }

  if (!coreWaitPromise) {
    coreWaitPromise = createCoreWait(baseUrl, maxWaitMs)
  }

  return coreWaitPromise
}

async function createCoreWait(
  baseUrl?: string,
  maxWaitMs: number = BOOTSTRAP_MAX_WAIT_MS,
): Promise<void> {
  const url = baseUrl ?? (await resolveBackendBaseUrl())

  if (await probeCoreReady(url)) {
    markCoreReady()
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
      markCoreReady()
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

    pollTimer = setInterval(() => {
      void probeCoreReady(url).then((ready) => {
        if (ready) finish()
      })
    }, BOOTSTRAP_POLL_INTERVAL_MS)
  })
}

function startCoreWatch(baseUrl: string): void {
  void waitForCoreReady(baseUrl)
}

export function useBackend(): BackendState {
  const ready = ref(false)
  const coreReady = ref(false)
  /** True only during the first health handshake; UI stays visible meanwhile. */
  const loading = ref(false)
  const error = ref<string | null>(null)
  const baseUrl = ref('')
  const startupProgress = ref<number | null>(null)

  let unlistenProgress: (() => void) | undefined

  async function init(): Promise<void> {
    error.value = null
    ready.value = false
    coreReady.value = false
    loading.value = true
    startupProgress.value = null
    resetCoreReady()

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
      startCoreWatch(url)
      if (isCoreReady()) {
        coreReady.value = true
      } else {
        void waitForCoreReady(url).then(() => {
          coreReady.value = true
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
  })

  return { ready, coreReady, loading, error, baseUrl, startupProgress, init }
}
