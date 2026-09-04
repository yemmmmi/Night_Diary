import { getHttpClient } from '@/shared/api/http'

export interface Conversation {
  id: string
  title: string
  active_replier_id: string
  created_at: string
  updated_at: string
}

export interface ChatMessage {
  id: string
  conversation_id: string
  role: 'user' | 'assistant'
  content: string
  retrieved_diary_ids?: number[]
  retrieved_memory_ids?: string[]
  attached_card_ids?: string[]
  attached_plan_ids?: string[]
  skill_result?: SkillResult | null
  created_at: string
}

/* ── 技能结果（记录 / 洞悉 / 计划）：随 assistant 消息落库的结构化产出 ── */

export interface RecordSkillResult {
  skill: 'record'
  diary_id: number
  date: string
  content: string
}

export interface InsightSkillResult {
  skill: 'insight'
  matched_theories: string[]
  observations: string[]
}

export interface PlanSkillNode {
  id: string
  title: string
  note: string
  link: string | null
  verified: boolean
}

export interface PlanSkillResult {
  skill: 'plan'
  plan_id: string
  template: 'checkin_total' | 'timer_daily' | 'milestones'
  title: string
  target_value: number | null
  target_unit: string | null
  tasks: PlanSkillNode[]
}

export type SkillResult = RecordSkillResult | InsightSkillResult | PlanSkillResult

/* 用户可手动指定的技能（笔谈输入区 chips） */
export type UserSkill = 'record' | 'insight' | 'plan'

export interface SendMessagePayload {
  content: string
  diary_ids?: number[]
  card_ids?: string[]
  plan_ids?: string[]
  auto_retrieve?: boolean
  skill?: UserSkill
}

export interface SendMessageResponse {
  message: ChatMessage
  reply: ChatMessage
}

export interface GenerateCardPayload {
  emotion: string
  event_summary: string
  tags: string[]
}

export async function listConversations(): Promise<Conversation[]> {
  const client = await getHttpClient()
  const { data } = await client.get<Conversation[]>('/api/v1/conversations')
  return data
}

export async function createConversation(): Promise<Conversation> {
  const client = await getHttpClient()
  const { data } = await client.post<Conversation>('/api/v1/conversations')
  return data
}

export async function deleteConversation(id: string): Promise<void> {
  const client = await getHttpClient()
  await client.delete(`/api/v1/conversations/${id}`)
}

export async function getMessages(conversationId: string): Promise<ChatMessage[]> {
  const client = await getHttpClient()
  const { data } = await client.get<ChatMessage[]>(
    `/api/v1/conversations/${conversationId}/messages`,
  )
  return data
}

export async function sendMessage(
  conversationId: string,
  payload: SendMessagePayload,
): Promise<SendMessageResponse> {
  const client = await getHttpClient()
  const { data } = await client.post<SendMessageResponse>(
    `/api/v1/conversations/${conversationId}/messages`,
    payload,
  )
  return data
}

export async function generateCardSummary(
  conversationId: string,
): Promise<GenerateCardPayload> {
  const client = await getHttpClient()
  const { data } = await client.post<GenerateCardPayload>(
    `/api/v1/conversations/${conversationId}/generate-card`,
  )
  return data
}

export interface SendMessageStreamingResponse {
  streaming: boolean
  trace_id: string
}

export async function sendMessageStreaming(
  conversationId: string,
  payload: SendMessagePayload,
  traceId?: string,
): Promise<SendMessageStreamingResponse> {
  const client = await getHttpClient()
  const headers: Record<string, string> = {}
  if (traceId) headers['X-Trace-Id'] = traceId
  const { data } = await client.post<SendMessageStreamingResponse>(
    `/api/v1/conversations/${conversationId}/messages/stream`,
    payload,
    { headers },
  )
  return data
}

export async function abortStreaming(
  conversationId: string,
  traceId: string,
): Promise<{ cancelled: boolean }> {
  const client = await getHttpClient()
  const { data } = await client.post<{ cancelled: boolean }>(
    `/api/v1/conversations/${conversationId}/messages/abort`,
    { trace_id: traceId },
  )
  return data
}
