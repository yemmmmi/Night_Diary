import { getHttpClient } from '@/shared/api/http'

/** A user-authored, safety-reviewed custom skill (A2). */
export interface CustomSkill {
  id: number
  name: string
  description: string
  triggers: string[]
  instruction: string
  enabled: boolean
  version: number
  created_at: number
  updated_at: number
}

export interface CustomSkillInput {
  name: string
  description?: string
  triggers: string[]
  instruction: string
  enabled?: boolean
}

export interface CustomSkillVersion {
  version: number
  name: string
  description: string
  triggers: string[]
  instruction: string
  enabled: boolean
  created_at: number
}

export async function listCustomSkills(): Promise<CustomSkill[]> {
  const client = await getHttpClient()
  const { data } = await client.get<CustomSkill[]>('/api/v1/custom-skills')
  return data
}

export async function createCustomSkill(body: CustomSkillInput): Promise<CustomSkill> {
  const client = await getHttpClient()
  const { data } = await client.post<CustomSkill>('/api/v1/custom-skills', body)
  return data
}

export async function updateCustomSkill(
  id: number,
  body: CustomSkillInput,
): Promise<CustomSkill> {
  const client = await getHttpClient()
  const { data } = await client.patch<CustomSkill>(`/api/v1/custom-skills/${id}`, body)
  return data
}

export async function setCustomSkillEnabled(
  id: number,
  enabled: boolean,
): Promise<CustomSkill> {
  const client = await getHttpClient()
  const { data } = await client.patch<CustomSkill>(`/api/v1/custom-skills/${id}/enabled`, {
    enabled,
  })
  return data
}

export async function deleteCustomSkill(id: number): Promise<void> {
  const client = await getHttpClient()
  await client.delete(`/api/v1/custom-skills/${id}`)
}

export async function listCustomSkillVersions(id: number): Promise<CustomSkillVersion[]> {
  const client = await getHttpClient()
  const { data } = await client.get<CustomSkillVersion[]>(
    `/api/v1/custom-skills/${id}/versions`,
  )
  return data
}