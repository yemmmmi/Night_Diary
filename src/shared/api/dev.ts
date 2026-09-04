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

export interface McpEndpointStatus {
  alias: string
  transport: 'sse' | 'stdio'
  state: 'healthy' | 'unhealthy' | 'dead'
  tool_count: number
  restart_count: number
  last_error: string
  loaded_at: string
}

export interface McpToolInfo {
  name: string
  description: string
  source: string
  transport: string
}

export interface McpCallLog {
  id: string
  user_id: string | null
  trace_id: string | null
  endpoint_alias: string
  transport: string
  tool_name: string
  raw_tool_name: string
  status: string
  duration_ms: number
  error_message: string | null
  arguments_snapshot: string
  result_snapshot: string
  created_at: number
}

export async function getMcpStatus(): Promise<{ items: McpEndpointStatus[] }> {
  const client = await getHttpClient()
  const { data } = await client.get('/api/v1/dev/mcp/status')
  return data
}

export async function getMcpTools(): Promise<{ items: McpToolInfo[] }> {
  const client = await getHttpClient()
  const { data } = await client.get('/api/v1/dev/mcp/tools')
  return data
}

export async function getMcpCalls(params?: {
  endpoint?: string
  status?: string
  user?: string
  page?: number
  page_size?: number
}): Promise<{ items: McpCallLog[]; total: number }> {
  const client = await getHttpClient()
  const { data } = await client.get('/api/v1/dev/mcp/calls', { params })
  return data
}
