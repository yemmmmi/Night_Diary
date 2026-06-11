import axios, { type AxiosInstance } from 'axios'

import { resolveBackendBaseUrl, waitForBootstrapReady } from '@/shared/composables/useBackend'

export {
  resolveBackendBaseUrl,
  useBackend,
  waitForBackendHealth,
  waitForBootstrapReady,
} from '@/shared/composables/useBackend'

let httpClient: AxiosInstance | null = null
let httpClientBaseUrl: string | null = null

export async function getHttpClient(): Promise<AxiosInstance> {
  const baseURL = await resolveBackendBaseUrl()
  await waitForBootstrapReady(baseURL)

  if (httpClient && httpClientBaseUrl === baseURL) {
    return httpClient
  }

  httpClient = axios.create({
    baseURL,
    timeout: 30_000,
    headers: { Accept: 'application/json' },
  })
  httpClientBaseUrl = baseURL

  return httpClient
}

export function resetHttpClient(): void {
  httpClient = null
  httpClientBaseUrl = null
}
