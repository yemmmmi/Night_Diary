import { getHttpClient } from '@/shared/api/http'

export type ModelTier = 'light' | 'medium' | 'heavy' | 'default'

export interface ModelProvider {
  id: number
  model_name: string
  base_url: string | null
  tier: ModelTier
  is_active: boolean
  is_default: boolean
  has_api_key: boolean
}

export interface ModelCreatePayload {
  model_name: string
  api_key: string
  base_url: string
  tier: ModelTier
  is_active: boolean
}

export interface ModelUpdatePayload {
  model_name?: string
  api_key?: string
  base_url?: string
  tier?: ModelTier
  is_active?: boolean
}

export async function listModels(): Promise<ModelProvider[]> {
  const client = await getHttpClient()
  const { data } = await client.get<ModelProvider[]>('/api/v1/models')
  return data
}

export async function createModel(payload: ModelCreatePayload): Promise<ModelProvider> {
  const client = await getHttpClient()
  const { data } = await client.post<ModelProvider>('/api/v1/models', payload)
  return data
}

export async function updateModel(
  modelId: number,
  payload: ModelUpdatePayload,
): Promise<ModelProvider> {
  const client = await getHttpClient()
  const { data } = await client.put<ModelProvider>(`/api/v1/models/${modelId}`, payload)
  return data
}

export async function deleteModel(modelId: number): Promise<void> {
  const client = await getHttpClient()
  await client.delete(`/api/v1/models/${modelId}`)
}
