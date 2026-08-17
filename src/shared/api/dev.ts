import { getHttpClient } from './http'

export interface TraceSummary {
  trace_id: string
  scenario: 'diary' | 'chat'
  status: 'completed' | 'error'
  started_at: string
  duration_ms: number
  span_count: number
  ref_id: string | null
}

export interface TraceSpan {
  span_id: string
  stage_name: string
  stage_label: string
  status: 'running' | 'completed' | 'error' | 'dispatched'
  duration_ms: number | null
  input_snapshot: Record<string, unknown>
  output_snapshot: Record<string, unknown>
  metadata: Record<string, unknown>
  child_spans: TraceSpan[]
  error: string | null
}

export interface PipelineTrace {
  trace_id: string
  scenario: 'diary' | 'chat'
  user_id: string
  status: 'running' | 'completed' | 'error'
  started_at: string
  ended_at: string | null
  duration_ms: number | null
  span_count: number
  spans: TraceSpan[]
}

export interface MiddlewareStatus {
  redis: boolean
  neo4j: boolean
  langgraph: boolean
  rq: boolean
  mysql: boolean
  llm: boolean
  rag: boolean
  episodic_memory: boolean
  treehole: boolean
  degraded: boolean
}

export async function listTraces(params?: {
  scenario?: string
  status?: string
  ref_id?: string
  page?: number
  page_size?: number
}): Promise<{ items: TraceSummary[]; total: number }> {
  const client = await getHttpClient()
  const { data } = await client.get('/api/v1/dev/traces', { params })
  return data
}

export async function getTrace(traceId: string): Promise<PipelineTrace> {
  const client = await getHttpClient()
  const { data } = await client.get(`/api/v1/dev/traces/${traceId}`)
  return data
}

export async function deleteTrace(traceId: string): Promise<void> {
  const client = await getHttpClient()
  await client.delete(`/api/v1/dev/traces/${traceId}`)
}

export async function getDevStats(): Promise<{
  total_traces: number
  by_scenario: Record<string, number>
  avg_duration_ms: number
  error_count: number
}> {
  const client = await getHttpClient()
  const { data } = await client.get('/api/v1/dev/stats')
  return data
}

export async function getMiddlewareStatus(): Promise<MiddlewareStatus> {
  const client = await getHttpClient()
  const { data } = await client.get('/api/v1/dev/middleware-status')
  return data
}
