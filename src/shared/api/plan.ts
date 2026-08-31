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
  actual_value: number | null
}

export interface PlanItem {
  id: string
  title: string
  motivation: string | null
  source_refs: SourceRef[]
  status: 'active' | 'archived' | 'completed'
  source: 'manual' | 'agent'
  tasks: TaskItem[]
  recurrence: string | null
  target_value: number | null
  target_unit: string | null
  target_period: 'daily' | 'weekly' | 'total' | null
}

export async function createPlan(payload: {
  title: string
  motivation?: string
  source_refs?: SourceRef[]
  tasks?: Array<{ title: string; note?: string; due_date?: string }>
  source?: 'manual' | 'agent'
  created_from_conversation_id?: string
  recurrence?: string
  target_value?: number
  target_unit?: string
  target_period?: 'daily' | 'weekly' | 'total'
}): Promise<PlanItem> {
  const client = await getHttpClient()
  const { data } = await client.post<PlanItem>('/api/v1/plans', payload)
  return data
}

/** 创建独立任务（plan_id 可选；今日待办的快速添加走这里）。 */
export async function createTask(payload: {
  title: string
  note?: string
  due_date?: string
  plan_id?: string
}): Promise<TaskItem> {
  const client = await getHttpClient()
  const { data } = await client.post<TaskItem>('/api/v1/tasks', payload)
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

export interface ListTasksParams {
  plan_id?: string
  status?: string
  date_from?: string
  date_to?: string
}

export async function listTasks(params: ListTasksParams = {}): Promise<TaskItem[]> {
  const client = await getHttpClient()
  const { data } = await client.get<TaskItem[]>('/api/v1/tasks', { params })
  return data
}

export async function updateTaskStatus(
  taskId: string,
  status: 'pending' | 'done' | 'skipped',
  actualValue?: number,
): Promise<TaskItem> {
  const client = await getHttpClient()
  const payload: Record<string, unknown> = { status }
  if (actualValue != null && status === 'done') payload.actual_value = actualValue
  const { data } = await client.patch<TaskItem>(`/api/v1/tasks/${taskId}`, payload)
  return data
}

/** 通用任务字段更新（V3.2 adjust 提案确认用；title/note/due_date 均可选）。 */
export async function updateTask(
  taskId: string,
  changes: Partial<Pick<TaskItem, 'title' | 'note' | 'due_date'>>,
): Promise<TaskItem> {
  const client = await getHttpClient()
  const { data } = await client.patch<TaskItem>(`/api/v1/tasks/${taskId}`, changes)
  return data
}

/** 计划字段更新（adjust / archive 确认用；title/motivation/status 可选）。 */
export async function updatePlan(
  planId: string,
  changes: Partial<Pick<PlanItem, 'title' | 'motivation' | 'status'>>,
): Promise<PlanItem> {
  const client = await getHttpClient()
  const { data } = await client.patch<PlanItem>(`/api/v1/plans/${planId}`, changes)
  return data
}

/** 归档任务：任务无 archived 态，映射为 skipped（V3.2）。 */
export async function archiveTask(taskId: string): Promise<TaskItem> {
  const client = await getHttpClient()
  const { data } = await client.patch<TaskItem>(`/api/v1/tasks/${taskId}`, {
    status: 'skipped',
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
