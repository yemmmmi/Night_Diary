import { getHttpClient } from '@/shared/api/http'

export type UserMode = 'daily' | 'followup' | 'introspection'

export interface ModeState {
  mode: UserMode
  display_name: string
}

export async function getCurrentMode(): Promise<ModeState> {
  const client = await getHttpClient()
  const { data } = await client.get<ModeState>('/api/v1/mode')
  return data
}

export async function overrideMode(mode: UserMode): Promise<ModeState> {
  const client = await getHttpClient()
  const { data } = await client.post<ModeState>('/api/v1/mode', { mode })
  return data
}
