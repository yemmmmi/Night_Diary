import { getHttpClient } from '@/shared/api/http'

export interface Tag {
  id: number
  name: string
  color: string
  usage_count?: number
  created_at?: string
}

export interface TagCreatePayload {
  name: string
  color?: string
}

export async function listTags(): Promise<Tag[]> {
  const client = await getHttpClient()
  const { data } = await client.get<Tag[]>('/api/v1/tags')
  return data
}

export async function createTag(payload: TagCreatePayload): Promise<Tag> {
  const client = await getHttpClient()
  const { data } = await client.post<Tag>('/api/v1/tags', payload)
  return data
}

export async function deleteTag(tagId: number): Promise<void> {
  const client = await getHttpClient()
  await client.delete(`/api/v1/tags/${tagId}`)
}

export async function seedMoodTags(): Promise<Tag[]> {
  const client = await getHttpClient()
  const { data } = await client.post<Tag[]>('/api/v1/tags/seed-mood')
  return data
}
