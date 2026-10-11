import { getHttpClient } from '@/shared/api/http'

export interface Tag {
  id: number
  name: string
  color: string
  usage_count: number
  created_at: string
}

export async function listTags(): Promise<Tag[]> {
  const client = await getHttpClient()
  const { data } = await client.get<Tag[]>('/api/v1/tags')
  return data
}