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
  created_at: string
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
  content: string,
): Promise<SendMessageResponse> {
  const client = await getHttpClient()
  const { data } = await client.post<SendMessageResponse>(
    `/api/v1/conversations/${conversationId}/messages`,
    { content },
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
