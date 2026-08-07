import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  listConversations,
  createConversation,
  deleteConversation,
  getMessages,
  sendMessage,
  sendMessageStreaming,
  generateCardSummary,
  type Conversation,
  type ChatMessage,
  type GenerateCardPayload,
} from '@/shared/api/conversation'
import { formatApiError } from '@/shared/utils/apiError'
import { useStreamingReply } from '@/shared/composables/useStreamingReply'
import { resolveBackendBaseUrl } from '@/shared/composables/useBackend'

export const useChatStore = defineStore('chat', () => {
  const conversations = ref<Conversation[]>([])
  const activeConversationId = ref<string | null>(null)
  const messages = ref<ChatMessage[]>([])
  const pinnedDiaryIds = ref<number[]>([])
  const autoRetrieve = ref(true)
  const loading = ref(false)
  const sending = ref(false)
  const error = ref<string | null>(null)

  // === 流式状态 ===
  // useStreamingReply 内部使用 onUnmounted，在 setup store（函数形式的 defineStore）
  // 中调用是安全的：store 在首次访问时初始化，通常处于某个组件的 setup 上下文。
  // streamingReply 提供 replyText / status / citations 给 UI 直接消费。
  const streamingReply = useStreamingReply()
  // 默认关闭，需要通过设置页 / 环境变量 / localStorage 显式开启。
  const streamingEnabled = ref(false)

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
      if (streamingEnabled.value) {
        // === 流式路径 ===
        const traceId = crypto.randomUUID()

        // 先添加用户消息（流式回复由 SSE 推送，由组件直接消费 streamingReply.replyText）
        const userMsg: ChatMessage = {
          id: 'temp-user-' + Date.now(),
          conversation_id: convId,
          role: 'user',
          content,
          created_at: new Date().toISOString(),
        }
        messages.value = [...messages.value, userMsg]

        try {
          const result = await sendMessageStreaming(
            convId,
            {
              content,
              diary_ids:
                pinnedDiaryIds.value.length > 0
                  ? pinnedDiaryIds.value
                  : undefined,
              auto_retrieve: autoRetrieve.value,
            },
            traceId,
          )

          if (!result.streaming || !result.trace_id) {
            // 后端不支持流式 → 撤销用户消息，回退到同步路径（同步路径会重新添加用户消息）
            messages.value = messages.value.filter((m) => m.id !== userMsg.id)
            return await sendSync(content)
          }

          // 连接 SSE 推送（流式消息持久化由后端处理，前端只更新 UI）
          const baseURL = await resolveBackendBaseUrl()
          streamingReply.connect(
            `${baseURL}/api/v1/dev/traces/${result.trace_id}/stream`,
          )
          return true
        } catch (streamErr) {
          // 流式端点报错时，撤销乐观添加的用户消息并回退到同步路径
          messages.value = messages.value.filter((m) => m.id !== userMsg.id)
          throw streamErr
        }
      }

      // === 同步路径（默认） ===
      return await sendSync(content)
    } catch (err) {
      error.value = formatApiError(err, '发送消息失败')
      return false
    } finally {
      sending.value = false
    }
  }

  // 同步路径：保持原有行为不变（在流式关闭或后端不支持流式时使用）
  async function sendSync(content: string): Promise<boolean> {
    const convId = activeConversationId.value
    if (!convId) return false

    const result = await sendMessage(convId, {
      content,
      diary_ids: pinnedDiaryIds.value,
      auto_retrieve: autoRetrieve.value,
    })
    messages.value = [...messages.value, result.message, result.reply]
    return true
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

  function setPinnedDiaryIds(ids: number[]) {
    pinnedDiaryIds.value = ids.slice(0, 3)
  }

  function pinDiary(id: number) {
    if (pinnedDiaryIds.value.includes(id)) return
    if (pinnedDiaryIds.value.length >= 3) return
    pinnedDiaryIds.value = [...pinnedDiaryIds.value, id]
  }

  return {
    conversations,
    activeConversationId,
    messages,
    pinnedDiaryIds,
    autoRetrieve,
    loading,
    sending,
    error,
    streamingReply,
    streamingEnabled,
    loadConversations,
    openConversation,
    startNewConversation,
    removeConversation,
    send,
    generateCard,
    setPinnedDiaryIds,
    pinDiary,
  }
})
