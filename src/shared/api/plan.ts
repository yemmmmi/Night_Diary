import { getHttpClient } from '@/shared/api/http'

export interface SourceRef {
  type: 'diary' | 'episodic' | 'memory'
  id: string | number
  date?: string
  snippet?: string
}

export interface TaskItem {
  id: string
  plan_id: string | null
  title: string
  note: string | null
  due_date: string | null
  status: 'pending' | 'done' | 'skipped'
  source: 'manual' | 'agent'
  completed_at: string | null
}

export interface PlanItem {
  id: string
  title: string
  motivation: string | null
  source_refs: SourceRef[]
  status: 'active' | 'archived' | 'completed'
  source: 'manual' | 'agent'
  tasks: TaskItem[]
}

export async function createPlan(payload: {
  title: string
  motivation?: string
  source_refs?: SourceRef[]
  tasks?: Array<{ title: string; note?: string; due_date?: string }>
  source?: 'manual' | 'agent'
  created_from_conversation_id?: string
}): Promise<PlanItem> {
  const client = await getHttpClient()
  const { data } = await client.post<PlanItem>('/api/v1/plans', payload)
  return data
}

export async function listPlans(status?: string): Promise<PlanItem[]> {
  const client = await getHttpClient()
  const params = status ? { status } : {}
  const { data } = await client.get<PlanItem[]>('/api/v1/plans', { params })
  return data
}

export async function getTodayTasks(): Promise<TaskItem[]> {
  const client = await getHttpClient()
  const { data } = await client.get<TaskItem[]>('/api/v1/tasks/today')
  return data
}

export async function updateTaskStatus(
  taskId: string,
  status: 'pending' | 'done' | 'skipped',
): Promise<TaskItem> {
  const client = await getHttpClient()
  const { data } = await client.patch<TaskItem>(`/api/v1/tasks/${taskId}`, {
    status,
  })
  return data
}

export async function deleteTask(taskId: string): Promise<void> {
  const client = await getHttpClient()
  await client.delete(`/api/v1/tasks/${taskId}`)
}

export async function deletePlan(planId: string): Promise<void> {
  const client = await getHttpClient()
  await client.delete(`/api/v1/plans/${planId}`)
}
