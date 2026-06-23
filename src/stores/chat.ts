import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  listConversations,
  createConversation,
  deleteConversation,
  getMessages,
  sendMessage,
  generateCardSummary,
  type Conversation,
  type ChatMessage,
  type GenerateCardPayload,
} from '@/shared/api/conversation'
import { formatApiError } from '@/shared/utils/apiError'

export const useChatStore = defineStore('chat', () => {
  const conversations = ref<Conversation[]>([])
  const activeConversationId = ref<string | null>(null)
  const messages = ref<ChatMessage[]>([])
  const loading = ref(false)
  const sending = ref(false)
  const error = ref<string | null>(null)

  async function loadConversations() {
    loading.value = true
    error.value = null
    try {
      conversations.value = await listConversations()
    } catch (err) {
      error.value = formatApiError(err, '加载会话列表失败')
    } finally {
      loading.value = false
    }
  }

  async function openConversation(id: string) {
    activeConversationId.value = id
    loading.value = true
    error.value = null
    try {
      messages.value = await getMessages(id)
    } catch (err) {
      error.value = formatApiError(err, '加载消息失败')
    } finally {
      loading.value = false
    }
  }

  async function startNewConversation(): Promise<Conversation | null> {
    error.value = null
    try {
      const conv = await createConversation()
      conversations.value = [conv, ...conversations.value]
      activeConversationId.value = conv.id
      messages.value = []
      return conv
    } catch (err) {
      error.value = formatApiError(err, '创建会话失败')
      return null
    }
  }

  async function removeConversation(id: string) {
    error.value = null
    try {
      await deleteConversation(id)
      conversations.value = conversations.value.filter((c) => c.id !== id)
      if (activeConversationId.value === id) {
        activeConversationId.value = null
        messages.value = []
      }
    } catch (err) {
      error.value = formatApiError(err, '删除会话失败')
    }
  }

  async function send(content: string): Promise<boolean> {
    const convId = activeConversationId.value
    if (!convId) return false
    sending.value = true
    error.value = null
    try {
      const result = await sendMessage(convId, content)
      messages.value = [...messages.value, result.message, result.reply]
      return true
    } catch (err) {
      error.value = formatApiError(err, '发送消息失败')
      return false
    } finally {
      sending.value = false
    }
  }

  async function generateCard(): Promise<GenerateCardPayload | null> {
    const convId = activeConversationId.value
    if (!convId) return null
    error.value = null
    try {
      return await generateCardSummary(convId)
    } catch (err) {
      error.value = formatApiError(err, '生成卡片失败')
      return null
    }
  }

  return {
    conversations,
    activeConversationId,
    messages,
    loading,
    sending,
    error,
    loadConversations,
    openConversation,
    startNewConversation,
    removeConversation,
    send,
    generateCard,
  }
})
