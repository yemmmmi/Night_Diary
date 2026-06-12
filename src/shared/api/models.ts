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

export interface ModelTierStatus {
  tier: ModelTier
  configured: boolean
  model_name: string | null
  base_url: string | null
  is_active: boolean
}

export interface ModelStatusResponse {
  tiers: ModelTierStatus[]
  env_fallback: boolean
  env_model_name: string | null
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

export interface ModelTestConnectionPayload {
  model_name: string
  api_key: string
  base_url: string
}

export interface ModelTestConnectionResult {
  ok: boolean
  message: string | null
}

export async function listModels(): Promise<ModelProvider[]> {
  const client = await getHttpClient()
  const { data } = await client.get<ModelProvider[]>('/api/v1/models')
  return data
}

export async function getModelsStatus(): Promise<ModelStatusResponse> {
  const client = await getHttpClient()
  const { data } = await client.get<ModelStatusResponse>('/api/v1/models/status')
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

export async function testModelConnection(
  payload: ModelTestConnectionPayload,
): Promise<ModelTestConnectionResult> {
  const client = await getHttpClient()
  const { data } = await client.post<ModelTestConnectionResult>(
    '/api/v1/models/test-connection',
    payload,
  )
  return data
}

export async function testStoredModelConnection(modelId: number): Promise<ModelTestConnectionResult> {
  const client = await getHttpClient()
  const { data } = await client.post<ModelTestConnectionResult>(
    `/api/v1/models/${modelId}/test-connection`,
  )
  return data
}
