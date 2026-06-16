import { getHttpClient } from '@/shared/api/http'

export type ModelDownloadPhase = 'pending' | 'downloading' | 'ready' | 'error' | 'skipped'

export interface ModelDownloadItem {
  key: string
  repo_id: string
  status: ModelDownloadPhase
  progress: number
  error: string | null
}

export interface ModelDownloadStatus {
  items: ModelDownloadItem[]
  overall_progress: number
  all_ready: boolean
  downloading: boolean
}

export async function getModelDownloadStatus(): Promise<ModelDownloadStatus> {
  const client = await getHttpClient()
  const { data } = await client.get<ModelDownloadStatus>('/api/v1/models/download/status')
  return data
}

export async function startModelDownload(): Promise<{ status: string }> {
  const client = await getHttpClient()
  const { data } = await client.post<{ status: string }>('/api/v1/models/download/start')
  return data
}
