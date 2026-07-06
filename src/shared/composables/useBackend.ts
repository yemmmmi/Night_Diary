import { onMounted, ref, type Ref } from 'vue'

const DEFAULT_DEV_BASE_URL = 'http://127.0.0.1:8000'
const HEALTH_PATH = '/health'
const READY_PATH = '/ready'
const HEALTH_INTERVAL_MS = 150
const HEALTH_MAX_ATTEMPTS = 150
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

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

export async function resolveBackendBaseUrl(): Promise<string> {
  return import.meta.env.VITE_API_BASE_URL ?? DEFAULT_DEV_BASE_URL
}

async function probeBackendHealth(baseUrl: string): Promise<boolean> {
  try {
    const url = new URL(HEALTH_PATH, baseUrl).toString()
    const response = await fetch(url)
    return response.ok
  } catch {
    return false
  }
}

async function probeCoreReady(baseUrl: string): Promise<boolean> {
  try {
    const url = new URL(READY_PATH, baseUrl).toString()
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
    const timers: { poll?: ReturnType<typeof setInterval> } = {}

    const cleanup = () => {
      if (timers.poll !== undefined) clearInterval(timers.poll)
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

    timers.poll = setInterval(() => {
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

  async function init(): Promise<void> {
    error.value = null
    ready.value = false
    coreReady.value = false
    loading.value = true
    startupProgress.value = null
    resetCoreReady()

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

  return { ready, coreReady, loading, error, baseUrl, startupProgress, init }
}
