import { getHttpClient } from '@/shared/api/http'

export interface ScheduledTaskKind {
  kind: string
  label: string
  default_mode: string
  allowed_modes: string[]
}

export interface ScheduledTask {
  id: string
  kind: string
  kind_label: string
  mode: string
  mode_label: string
  sink: string
  cron_expr: string
  payload: Record<string, unknown>
  enabled: boolean
  next_run_at: string | null
  last_run_at: string | null
  last_status: string | null
  created_at: string | null
}

export interface ScheduledTaskRun {
  id: number
  task_id: string
  kind: string
  status: string
  summary: string | null
  error: string | null
  started_at: string | null
  finished_at: string | null
}

export interface ScheduledTaskCreate {
  kind: string
  cron_expr: string
  payload?: Record<string, unknown>
  enabled?: boolean
  mode?: string
  sink?: string
}

export interface ScheduledTaskUpdate {
  cron_expr?: string
  payload?: Record<string, unknown>
  enabled?: boolean
  mode?: string
  sink?: string
}

export async function listKinds(): Promise<ScheduledTaskKind[]> {
  const client = await getHttpClient()
  const { data } = await client.get<ScheduledTaskKind[]>('/api/v1/schedules/kinds')
  return data
}

export async function listSchedules(): Promise<ScheduledTask[]> {
  const client = await getHttpClient()
  const { data } = await client.get<ScheduledTask[]>('/api/v1/schedules')
  return data
}

export async function createSchedule(body: ScheduledTaskCreate): Promise<ScheduledTask> {
  const client = await getHttpClient()
  const { data } = await client.post<ScheduledTask>('/api/v1/schedules', body)
  return data
}

export async function updateSchedule(
  id: string,
  patch: ScheduledTaskUpdate,
): Promise<ScheduledTask> {
  const client = await getHttpClient()
  const { data } = await client.patch<ScheduledTask>(`/api/v1/schedules/${id}`, patch)
  return data
}

export async function deleteSchedule(id: string): Promise<void> {
  const client = await getHttpClient()
  await client.delete(`/api/v1/schedules/${id}`)
}

export async function triggerSchedule(id: string): Promise<ScheduledTask> {
  const client = await getHttpClient()
  const { data } = await client.post<ScheduledTask>(`/api/v1/schedules/${id}/trigger`)
  return data
}

export async function listRuns(id: string, limit = 20): Promise<ScheduledTaskRun[]> {
  const client = await getHttpClient()
  const { data } = await client.get<ScheduledTaskRun[]>(`/api/v1/schedules/${id}/runs`, {
    params: { limit },
  })
  return data
}