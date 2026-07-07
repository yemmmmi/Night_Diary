import axios, { type AxiosInstance, isAxiosError } from 'axios'

import {
  resolveBackendBaseUrl,
  waitForCoreReady,
} from '@/shared/composables/useBackend'

export {
  resolveBackendBaseUrl,
  useBackend,
  waitForBackendHealth,
  waitForCoreReady,
} from '@/shared/composables/useBackend'

const BOOTSTRAP_RETRY_MS = 300
const BOOTSTRAP_MAX_RETRIES = 120

let httpClient: AxiosInstance | null = null
let httpClientBaseUrl: string | null = null

function isBootstrap503(err: unknown): boolean {
  if (!isAxiosError(err) || err.response?.status !== 503) {
    return false
  }
  const detail = err.response.data
  if (typeof detail === 'object' && detail !== null && 'detail' in detail) {
    const message = String((detail as { detail: unknown }).detail)
    return message.includes('初始化')
  }
  return true
}

async function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function requestWithBootstrapRetry<T>(
  baseURL: string,
  request: () => Promise<T>,
): Promise<T> {
  for (let attempt = 0; attempt < BOOTSTRAP_MAX_RETRIES; attempt += 1) {
    try {
      return await request()
    } catch (err) {
      if (!isBootstrap503(err) || attempt === BOOTSTRAP_MAX_RETRIES - 1) {
        throw err
      }
      await sleep(BOOTSTRAP_RETRY_MS)
      await waitForCoreReady(baseURL, BOOTSTRAP_RETRY_MS * 2)
    }
  }
  throw new Error('AI 引擎初始化超时')
}

export async function getHttpClient(): Promise<AxiosInstance> {
  const baseURL = await resolveBackendBaseUrl()

  if (httpClient && httpClientBaseUrl === baseURL) {
    return httpClient
  }

  const client = axios.create({
    baseURL,
    timeout: 30_000,
    headers: { Accept: 'application/json' },
  })

  // JWT 请求拦截器：自动附加 Authorization 头 + 开发者模式头
  client.interceptors.request.use((config) => {
    const token = localStorage.getItem('night_diary_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }

    // 开发者模式：附加 X-Developer-Mode 和 X-Trace-Id 头
    const settingsRaw = localStorage.getItem('night-diary-app-settings')
    if (settingsRaw) {
      try {
        const settings = JSON.parse(settingsRaw)
        if (settings.developerMode) {
          config.headers['X-Developer-Mode'] = 'true'
          if (!config.headers['X-Trace-Id']) {
            const activeId = localStorage.getItem('night-diary-active-trace-id')
            if (activeId) {
              config.headers['X-Trace-Id'] = activeId
            }
          }
        }
      } catch {
        // ignore parse errors
      }
    }

    return config
  })

  // bootstrap 503 重试拦截器（保留原有逻辑）
  client.interceptors.response.use(
    (response) => response,
    async (error) => {
      const config = error.config as
        | (NonNullable<typeof error.config> & { __bootstrapRetryCount?: number })
        | undefined
      if (!config || !isBootstrap503(error)) {
        return Promise.reject(error)
      }

      config.__bootstrapRetryCount = (config.__bootstrapRetryCount ?? 0) + 1
      if (config.__bootstrapRetryCount > BOOTSTRAP_MAX_RETRIES) {
        return Promise.reject(error)
      }

      await sleep(BOOTSTRAP_RETRY_MS)
      return client.request(config)
    },
  )

  // 401 响应拦截器：令牌失效时清理本地状态并跳转登录页
  client.interceptors.response.use(
    (response) => response,
    (error) => {
      if (isAxiosError(error) && error.response?.status === 401) {
        localStorage.removeItem('night_diary_token')
        // 避免在登录页面循环跳转
        if (!window.location.hash.includes('/login')) {
          window.location.hash = '#/login'
        }
      }
      return Promise.reject(error)
    },
  )

  httpClient = client
  httpClientBaseUrl = baseURL

  return httpClient
}

/** Run an API call; retries while the backend bootstrap returns 503. */
export async function apiRequest<T>(request: () => Promise<T>): Promise<T> {
  const baseURL = await resolveBackendBaseUrl()
  return requestWithBootstrapRetry(baseURL, request)
}

export function resetHttpClient(): void {
  httpClient = null
  httpClientBaseUrl = null
}
