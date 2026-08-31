import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'

import type { ChatMessage, Conversation } from '@/shared/api/conversation'
import type { DiaryEntry } from '@/shared/api/diary'
import type { MemoryCard } from '@/shared/api/card'
import type { StreamingReplyStatus } from '@/shared/composables/useStreamingReply'

const push = vi.fn()
let routeQuery: Record<string, string> = {}

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: routeQuery, params: {} }),
  useRouter: () => ({ push }),
}))

const listConversations = vi.hoisted(() => vi.fn(async () => [] as Conversation[]))
const createConversation = vi.hoisted(() => vi.fn())
const deleteConversation = vi.hoisted(() => vi.fn(async () => undefined))
const getMessages = vi.hoisted(() => vi.fn(async () => [] as ChatMessage[]))
const sendMessage = vi.hoisted(() => vi.fn())
const sendMessageStreaming = vi.hoisted(() => vi.fn())
const generateCardSummary = vi.hoisted(() => vi.fn())
const abortStreaming = vi.hoisted(() => vi.fn(async () => ({ cancelled: true })))

vi.mock('@/shared/api/conversation', () => ({
  listConversations,
  createConversation,
  deleteConversation,
  getMessages,
  sendMessage,
  sendMessageStreaming,
  generateCardSummary,
  abortStreaming,
}))

const listDiaryEntries = vi.hoisted(() => vi.fn(async () => [] as DiaryEntry[]))
vi.mock('@/shared/api/diary', () => ({ listDiaryEntries }))

const listCards = vi.hoisted(() => vi.fn(async () => [] as MemoryCard[]))
vi.mock('@/shared/api/card', () => ({ listCards }))

const getCurrentMode = vi.hoisted(() => vi.fn(async () => ({ mode: 'daily', display_name: '日常' })))
const overrideMode = vi.hoisted(() => vi.fn(async () => ({ mode: 'daily', display_name: '日常' })))
vi.mock('@/shared/api/mode', () => ({ getCurrentMode, overrideMode }))

import ChatScene from '@/pages/ChatScene.vue'
import { useChatStore } from '@/stores/chat'
import { useSettingsStore } from '@/stores/settings'

function conv(id: string, title: string): Conversation {
  return {
    id,
    title,
    active_replier_id: 'night',
    created_at: '2026-01-02T09:00:00',
    updated_at: '2026-01-02T09:00:00',
  }
}

function msg(
  id: string,
  role: 'user' | 'assistant',
  content: string,
  extra: Partial<ChatMessage> = {},
): ChatMessage {
  return {
    id,
    conversation_id: 'c1',
    role,
    content,
    created_at: '2026-01-02T21:00:00',
    ...extra,
  }
}

function diary(id: number, content: string): DiaryEntry {
  return {
    id,
    content,
    date: '2026-01-01',
    weather: null,
    reply: null,
    created_at: '2026-01-01T21:00:00',
    updated_at: '2026-01-01T21:00:00',
  }
}

/** pinia 的 reactive store 会解包嵌套 ref，这里以运行时视角写入流式状态。 */
function setStreamingState(
  chatStore: ReturnType<typeof useChatStore>,
  status: StreamingReplyStatus,
  text: string,
): void {
  Object.assign(chatStore.streamingReply as unknown as { status: StreamingReplyStatus; replyText: string }, {
    status,
    replyText: text,
  })
}

class StubEventSource {
  close(): void {}
  addEventListener(): void {}
  removeEventListener(): void {}
}

interface SceneOptions {
  messages?: ChatMessage[]
  conversations?: Conversation[]
  developerMode?: boolean
}

function mountScene(options: SceneOptions = {}) {
  setActivePinia(createPinia())
  const chatStore = useChatStore()
  const settings = useSettingsStore()
  settings.load()
  if (options.developerMode) settings.developerMode = true

  const conversations = options.conversations ?? []
  const messages = options.messages ?? []
  listConversations.mockResolvedValue(conversations)
  chatStore.conversations = conversations
  chatStore.activeConversationId = messages.length > 0 ? messages[0].conversation_id : null
  chatStore.messages = messages

  const wrapper = mount(ChatScene, {
    // @vue/test-utils 默认把 Transition/TransitionGroup 替换成 <transition-group-stub>，
    // 那样永远看不到 letter-enter-* 过渡类。这里显式关掉默认 stub，用真实过渡实现。
    global: {
      stubs: {
        transition: false,
        'transition-group': false,
      },
    },
  })
  return { wrapper, chatStore, settings }
}

/** 只冲刷微任务队列：不触发 requestAnimationFrame，保住 enter 过渡类。 */
async function flushMicrotasks(rounds = 10): Promise<void> {
  for (let i = 0; i < rounds; i++) {
    await nextTick()
  }
}

/**
 * 冲刷宏任务队列：让 happy-dom 的 requestAnimationFrame（按宏任务调度）跑完
 * nextFrame 的两级回调，leave 过渡得以收尾、元素真正从 DOM 移除。
 */
async function flushMacrotasks(rounds = 8): Promise<void> {
  for (let i = 0; i < rounds; i++) {
    await new Promise((resolve) => {
      setTimeout(resolve, 0)
    })
    await nextTick()
  }
}

describe('ChatScene', () => {
  let warnSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    routeQuery = {}
    listDiaryEntries.mockResolvedValue([])
    listCards.mockResolvedValue([])
    listConversations.mockResolvedValue([])
    getMessages.mockResolvedValue([])
    sendMessage.mockResolvedValue({
      message: msg('m-u', 'user', '今天有点累'),
      reply: msg('m-a', 'assistant', '早点休息'),
    })
    sendMessageStreaming.mockResolvedValue({ streaming: false, trace_id: '' })
    getCurrentMode.mockResolvedValue({ mode: 'daily', display_name: '日常' })
    warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    warnSpy.mockRestore()
  })

  it('renders the exchange as letters with sender signature and time', async () => {
    const { wrapper } = mountScene({
      messages: [msg('m1', 'user', '今天有点累'), msg('m2', 'assistant', '累就早点休息')],
    })
    await flushPromises()

    const letters = wrapper.findAll('[data-testid="letter"]')
    expect(letters).toHaveLength(2)
    expect(wrapper.find('.chat-msg').exists()).toBe(false)
    expect(letters[0].text()).toContain('我')
    expect(letters[1].text()).toContain('夜记')
    expect(letters[0].find('.letter__time').text()).toMatch(/\d{1,2}:\d{2}/)
    expect(letters[1].find('.letter__time').text()).toMatch(/\d{1,2}:\d{2}/)
  })

  it('aligns the user signature to the right and the night signature to the left', async () => {
    const { wrapper } = mountScene({
      messages: [msg('m1', 'user', '今天有点累'), msg('m2', 'assistant', '累就早点休息')],
    })
    await flushPromises()

    const letters = wrapper.findAll('[data-testid="letter"]')
    expect(letters[0].classes()).toContain('letter--user')
    expect(letters[1].classes()).toContain('letter--assistant')
  })

  it('shows a collapsed margin note for referenced diaries and expands it on click', async () => {
    listDiaryEntries.mockResolvedValue([
      diary(11, '和白猫在楼道里坐了一会'),
      diary(12, '改完了简历的第三版'),
    ])
    const { wrapper } = mountScene({
      messages: [
        msg('m1', 'user', '最近发生了什么'),
        msg('m2', 'assistant', '你提到过和小猫的相处', { retrieved_diary_ids: [11, 12] }),
      ],
    })
    await flushPromises()

    const note = wrapper.find('[data-testid="letter-note"]')
    expect(note.exists()).toBe(true)
    expect(note.text()).toContain('参考了 2 篇日记')
    expect(wrapper.text()).not.toContain('白猫在楼道里')
    expect(wrapper.text()).not.toContain('改完了简历')

    await note.find('button').trigger('click')
    await nextTick()
    expect(wrapper.findAll('[data-testid="letter-note-item"]')).toHaveLength(2)
    expect(wrapper.text()).toContain('白猫在楼道里')
    expect(wrapper.text()).toContain('改完了简历')
  })

  it('hides the margin note when the reply references no diary', async () => {
    const { wrapper } = mountScene({
      messages: [msg('m1', 'assistant', '只是随口聊聊')],
    })
    await flushPromises()
    expect(wrapper.find('[data-testid="letter-note"]').exists()).toBe(false)
  })

  it('uses a bottom-line ink input for the reply box', async () => {
    const { wrapper } = mountScene({ messages: [msg('m1', 'user', '今天有点累')] })
    await flushPromises()

    const input = wrapper.find('[data-testid="letter-input"]')
    expect(input.exists()).toBe(true)
    expect(input.classes()).toContain('ink-underline')
    expect(input.find('textarea').exists()).toBe(true)
  })

  it('animates newly arrived letters with the letter-arrive transition', async () => {
    const { wrapper } = mountScene({ messages: [msg('m0', 'user', '想聊聊今天')] })
    await flushPromises()

    await wrapper.find('[data-testid="letter-input"] textarea').setValue('今天有点累')
    await wrapper.find('[data-testid="letter-send"]').trigger('click')
    await flushMicrotasks()

    const letters = wrapper.findAll('[data-testid="letter"]')
    expect(letters.length).toBeGreaterThanOrEqual(2)
    expect(letters.some((letter) => letter.classes().includes('letter-enter-active'))).toBe(true)
  })

  it('shows the in-progress letter from the streaming reply while writing', async () => {
    const { wrapper, chatStore } = mountScene({
      messages: [msg('m1', 'user', '今天有点累')],
    })
    await flushPromises()
    expect(wrapper.find('[data-testid="letter-streaming"]').exists()).toBe(false)

    setStreamingState(chatStore, 'streaming', '夜记落笔的第一段……')
    await nextTick()

    const streaming = wrapper.find('[data-testid="letter-streaming"]')
    expect(streaming.exists()).toBe(true)
    expect(streaming.text()).toContain('夜记落笔的第一段')
    expect(streaming.text()).toContain('夜记正在写')
    expect(wrapper.find('[data-testid="ink-grinding"]').exists()).toBe(true)

    setStreamingState(chatStore, 'done', '夜记落笔的第一段……')
    // 真实 TransitionGroup 的 leave 过渡要等 rAF 宏任务跑完才移除元素
    await flushMacrotasks()
    expect(wrapper.find('[data-testid="letter-streaming"]').exists()).toBe(false)
  })

  it('keeps the dev pipeline panel in the right rail only in developer mode', async () => {
    const { wrapper, settings } = mountScene({ messages: [msg('m1', 'user', '今天有点累')] })
    await flushPromises()

    expect(wrapper.find('.dev-pipeline-panel').exists()).toBe(false)
    expect(wrapper.find('.ref-panel').exists()).toBe(false)
    expect(wrapper.find('.output-panel').exists()).toBe(false)

    settings.developerMode = true
    await nextTick()
    expect(wrapper.find('.dev-pipeline-panel').exists()).toBe(true)
  })

  it('keeps the conversation list rail', async () => {
    const { wrapper } = mountScene({
      messages: [msg('m1', 'user', '今天有点累')],
      conversations: [conv('c1', '关于睡眠'), conv('c2', '关于工作')],
    })
    await flushPromises()

    const list = wrapper.find('[data-testid="conversation-list"]')
    expect(list.exists()).toBe(true)
    expect(list.text()).toContain('关于睡眠')
    expect(list.text()).toContain('关于工作')
  })

  it('uses quiet empty-state copy without the replier wording', async () => {
    const { wrapper } = mountScene({})
    await flushPromises()

    expect(wrapper.find('[data-testid="letter-input"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('回信者')
    expect(wrapper.text()).toContain('夜记在读')

    createConversation.mockResolvedValue(conv('c9', '新的一封'))
    await wrapper.find('[data-testid="new-letter"]').trigger('click')
    await flushPromises()
    expect(createConversation).toHaveBeenCalled()
  })

  it('pins the diary referenced by the route query deep link', async () => {
    routeQuery = { diaryId: '11' }
    listDiaryEntries.mockResolvedValue([])
    const { wrapper } = mountScene({ messages: [msg('m1', 'user', '今天有点累')] })
    await flushPromises()

    const chip = wrapper.find('.diary-picker__chip--selected')
    expect(chip.exists()).toBe(true)
    expect(chip.text()).toContain('11')
  })

  it('offers a save-as-memory-card link on the latest reply and confirms quietly', async () => {
    generateCardSummary.mockResolvedValue({
      emotion: 'calm',
      event_summary: '和夜记聊了睡眠',
      tags: [],
    })
    const { wrapper } = mountScene({
      messages: [
        msg('m1', 'user', '最近睡不好'),
        msg('m2', 'assistant', '我们聊聊睡前的事'),
        msg('m3', 'user', '再说说'),
        msg('m4', 'assistant', '好，慢慢说'),
      ],
    })
    await flushPromises()

    const links = wrapper.findAll('[data-testid="letter-card-link"]')
    expect(links).toHaveLength(1)
    expect(links[0].text()).toContain('存为记忆卡片')

    await links[0].trigger('click')
    await flushPromises()
    expect(generateCardSummary).toHaveBeenCalledWith('c1')
    expect(wrapper.text()).toContain('已收入记忆')
    expect(wrapper.find('[data-testid="letter-card-link"]').exists()).toBe(false)
  })

  it('reloads the conversation when a streaming reply ends', async () => {
    vi.stubGlobal('EventSource', StubEventSource)
    vi.stubGlobal('crypto', { randomUUID: () => 'trace-uuid-1' })
    sendMessageStreaming.mockResolvedValue({ streaming: true, trace_id: 'trace-1' })
    getMessages.mockResolvedValue([
      msg('m1', 'user', '今天有点累'),
      msg('m2', 'assistant', '早点休息，明天会轻一些'),
    ])

    const { wrapper, chatStore } = mountScene({ messages: [msg('m1', 'user', '今天有点累')] })
    await flushPromises()

    await wrapper.find('[data-testid="letter-input"] textarea').setValue('今天有点累')
    await wrapper.find('[data-testid="letter-send"]').trigger('click')
    await flushPromises()

    expect(sendMessageStreaming).toHaveBeenCalled()
    expect(sendMessage).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="letter-streaming"]').exists()).toBe(true)

    setStreamingState(chatStore, 'done', '早点休息，明天会轻一些')
    await flushPromises()
    // 流式信纸的 leave 过渡 + 重拉消息后的 enter 过渡都要等 rAF 宏任务收尾
    await flushMacrotasks()

    expect(getMessages).toHaveBeenCalledWith('c1')
    expect(wrapper.text()).toContain('明天会轻一些')
    expect(wrapper.find('[data-testid="letter-streaming"]').exists()).toBe(false)
  })
})
