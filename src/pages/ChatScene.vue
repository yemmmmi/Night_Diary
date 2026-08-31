<script setup lang="ts">
import { computed, nextTick, onActivated, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { chatCopy } from '@/shared/copy/chat'
import { listDiaryEntries, type DiaryEntry } from '@/shared/api/diary'
import { listCards, type MemoryCard } from '@/shared/api/card'
import { useChatStore } from '@/stores/chat'
import { useSettingsStore } from '@/stores/settings'
import { useDevStore } from '@/stores/dev'
import { diaryEntrySummary } from '@/shared/utils/diaryFormat'
import ConversationList from '@/features/chat/ConversationList.vue'
import LetterMessage from '@/features/chat/LetterMessage.vue'
import ChatInput from '@/features/chat/ChatInput.vue'
import DiaryReferencePicker from '@/features/chat/DiaryReferencePicker.vue'
import InkGrinding from '@/shared/components/InkGrinding.vue'
import DevPipelinePanel from '@/features/dev/DevPipelinePanel.vue'
import ModeBadge from '@/features/mode/ModeBadge.vue'

defineOptions({ name: 'ChatScene' })

const route = useRoute()
const chatStore = useChatStore()
const settings = useSettingsStore()
const devStore = useDevStore()
settings.load()

const messagesEl = ref<HTMLElement | null>(null)
const showDeleteConfirm = ref(false)
const pendingDeleteId = ref<string | null>(null)
const cardGenerating = ref(false)
const cardGenerated = ref(false)
const diaryCatalog = ref<DiaryEntry[]>([])
const referenceCards = ref<MemoryCard[]>([])
const modeBadge = ref<InstanceType<typeof ModeBadge> | null>(null)
const pendingUserText = ref<string | null>(null)

const diaryLabelMap = computed(() => {
  const map: Record<number, string> = {}
  for (const entry of diaryCatalog.value) {
    map[entry.id] = diaryEntrySummary(entry, referenceCards.value, 20)
  }
  return map
})

const lastAssistantId = computed(() => {
  for (let i = chatStore.messages.length - 1; i >= 0; i--) {
    if (chatStore.messages[i].role === 'assistant') return chatStore.messages[i].id
  }
  return null
})

/* 进行中的信：POST 发送期间（sending）与 SSE 书写期间（streamingActive）都算 */
const writingLetterVisible = computed(
  () => chatStore.sending || chatStore.streamingActive,
)

async function loadReferenceData() {
  try {
    const [diaries, cards] = await Promise.all([listDiaryEntries({ limit: 50 }), listCards()])
    diaryCatalog.value = diaries
    referenceCards.value = cards
  } catch {
    diaryCatalog.value = []
    referenceCards.value = []
  }
}

function applyRouteDiaryPin() {
  const raw = route.query.diaryId
  if (typeof raw !== 'string' || !raw.trim()) return
  const parsed = Number(raw)
  if (!Number.isFinite(parsed)) return
  chatStore.pinDiary(parsed)
}

function scrollToBottom() {
  nextTick(() => {
    requestAnimationFrame(() => {
      if (messagesEl.value) {
        messagesEl.value.scrollTop = messagesEl.value.scrollHeight
      }
    })
  })
}

async function onSelectConversation(id: string) {
  await chatStore.openConversation(id)
  scrollToBottom()
}

async function onNewConversation() {
  await chatStore.startNewConversation()
  scrollToBottom()
}

function onAskDelete(id: string) {
  pendingDeleteId.value = id
  showDeleteConfirm.value = true
}

async function onDeleteConfirm() {
  const id = pendingDeleteId.value
  showDeleteConfirm.value = false
  pendingDeleteId.value = null
  if (id) await chatStore.removeConversation(id)
}

async function onSend(text: string) {
  if (!chatStore.activeConversationId) {
    await chatStore.startNewConversation()
  }
  if (settings.developerMode) {
    devStore.setActiveTrace(crypto.randomUUID())
  }
  pendingUserText.value = text
  scrollToBottom()

  try {
    const ok = await chatStore.send(text)
    if (ok) {
      pendingUserText.value = null
    }
    scrollToBottom()
  } catch (e) {
    // On failure, clear the trace so the panel doesn't hang in "connecting".
    if (settings.developerMode) {
      devStore.setActiveTrace(null)
    }
    throw e
  }
  // NOTE: Do NOT clear activeTraceId here.  The SSE stream (useTraceStream)
  // is still draining span_complete events from the EventBus.  Clearing the
  // id now would close the EventSource before any events arrive, leaving the
  // panel stuck on "等待操作...".  The stream self-closes on trace_complete;
  // the next onSend() call replaces the id with a fresh one.
}

async function onGenerateCard() {
  if (cardGenerating.value) return
  cardGenerating.value = true
  const result = await chatStore.generateCard()
  cardGenerating.value = false
  if (result) {
    cardGenerated.value = true
  }
}

const messageTimeline = computed(() => {
  const items: Array<
    | { kind: 'divider'; key: string; date: string }
    | { kind: 'message'; key: string; message: (typeof chatStore.messages)[number] }
  > = []

  let currentDate = ''
  for (const message of chatStore.messages) {
    const date = message.created_at.slice(0, 10)
    if (date !== currentDate) {
      currentDate = date
      items.push({ kind: 'divider', key: `div-${date}-${items.length}`, date })
    }
    items.push({ kind: 'message', key: message.id, message })
  }

  if (pendingUserText.value && chatStore.activeConversationId) {
    const last = chatStore.messages.at(-1)
    const alreadyPersisted =
      last?.role === 'user' && last.content === pendingUserText.value
    if (!alreadyPersisted) {
      const date = new Date().toISOString().slice(0, 10)
      if (date !== currentDate) {
        items.push({ kind: 'divider', key: `div-${date}-pending`, date })
      }
      items.push({
        kind: 'message',
        key: 'pending-user-local',
        message: {
          id: 'pending-user-local',
          conversation_id: chatStore.activeConversationId,
          role: 'user',
          content: pendingUserText.value,
          created_at: new Date().toISOString(),
        },
      })
    }
  }

  return items
})

onMounted(async () => {
  await Promise.all([chatStore.loadConversations(), loadReferenceData()])
  modeBadge.value?.load()
  applyRouteDiaryPin()
})

onActivated(async () => {
  await chatStore.loadConversations()
  await loadReferenceData()
  applyRouteDiaryPin()
  if (chatStore.activeConversationId && !chatStore.sending) {
    await chatStore.openConversation(chatStore.activeConversationId)
    scrollToBottom()
  }
})

/* 流式落笔时信纸持续下坠，保持视口贴底 */
watch(
  () => chatStore.streamingText,
  () => {
    scrollToBottom()
  },
)

watch(
  () => chatStore.activeConversationId,
  () => {
    cardGenerated.value = false
    cardGenerating.value = false
  },
)
</script>

<template>
  <div class="chat-scene" :class="{ 'chat-scene--dev': settings.developerMode }">
    <!-- Left: conversation list -->
    <aside class="chat-scene__sidebar">
      <button type="button" class="chat-scene__new-link" @click="onNewConversation">
        {{ chatCopy.newConversation }}
      </button>
      <ConversationList
        :conversations="chatStore.conversations"
        :active-id="chatStore.activeConversationId"
        @select="onSelectConversation"
        @delete="onAskDelete"
      />
    </aside>

    <!-- Center: letter flow + composer -->
    <section class="chat-scene__main">
      <div class="chat-scene__bar">
        <ModeBadge ref="modeBadge" />
      </div>

      <!-- Empty state -->
      <div v-if="!chatStore.activeConversationId" class="chat-scene__empty">
        <p class="chat-scene__empty-title">{{ chatCopy.emptyTitle(settings.nickname) }}</p>
        <p class="chat-scene__empty-desc">{{ chatCopy.emptyDesc() }}</p>
        <button
          type="button"
          class="chat-scene__empty-link"
          data-testid="new-letter"
          @click="onNewConversation"
        >
          {{ chatCopy.newConversation }}
        </button>
      </div>

      <!-- Letters -->
      <template v-else>
        <div ref="messagesEl" class="chat-scene__messages">
          <TransitionGroup name="letter" tag="div" class="letter-flow">
            <template v-for="item in messageTimeline" :key="item.key">
              <p v-if="item.kind === 'divider'" class="letter-flow__divider">
                {{ chatCopy.dateDivider(item.date) }}
              </p>
              <LetterMessage
                v-else
                :message="item.message"
                :diary-labels="diaryLabelMap"
                :show-actions="item.message.id === lastAssistantId"
                :generating="cardGenerating"
                :generated="cardGenerated"
                @generate-card="onGenerateCard"
              />
            </template>

            <div
              v-if="writingLetterVisible"
              key="letter-streaming"
              class="writing-letter"
              data-testid="letter-streaming"
            >
              <header class="writing-letter__head">
                <span class="writing-letter__signature">{{ chatCopy.signatureNight }}</span>
              </header>
              <p v-if="chatStore.streamingText" class="writing-letter__body">
                {{ chatStore.streamingText }}
              </p>
              <p class="writing-letter__status">
                <InkGrinding size="sm" />
                <span>{{ chatCopy.writingLabel }}</span>
              </p>
            </div>
          </TransitionGroup>
        </div>

        <div class="chat-scene__composer">
          <DiaryReferencePicker
            v-model="chatStore.pinnedDiaryIds"
            :entries="diaryCatalog"
            :cards="referenceCards"
          />
          <div class="chat-scene__composer-row">
            <ChatInput
              :disabled="chatStore.sending || chatStore.streamingActive"
              @send="onSend"
            />
            <InkGrinding
              v-if="chatStore.sending || chatStore.streamingActive"
              size="sm"
              class="chat-scene__composer-ink"
            />
          </div>
        </div>
      </template>
    </section>

    <!-- Right: dev pipeline (developer mode only) -->
    <aside v-if="settings.developerMode" class="chat-scene__dev">
      <DevPipelinePanel />
    </aside>
  </div>

  <!-- Delete confirm -->
  <Teleport to="body">
    <div
      v-if="showDeleteConfirm"
      class="confirm-overlay"
      @click.self="showDeleteConfirm = false"
    >
      <div class="confirm-dialog">
        <p class="confirm-dialog__title">{{ chatCopy.confirmDelete }}</p>
        <p class="confirm-dialog__desc">{{ chatCopy.confirmDeleteDesc }}</p>
        <div class="confirm-dialog__actions">
          <button class="confirm-dialog__btn confirm-dialog__btn--cancel" @click="showDeleteConfirm = false">
            {{ chatCopy.cancel }}
          </button>
          <button class="confirm-dialog__btn confirm-dialog__btn--danger" @click="onDeleteConfirm">
            {{ chatCopy.confirm }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.chat-scene {
  display: grid;
  grid-template-columns: 11rem minmax(0, 1fr);
  /* titlebar 2.5rem + nav tabs ~3rem + app-shell frameless padding 2.5rem */
  height: calc(100dvh - 8rem);
  overflow: hidden;
  box-sizing: border-box;
}

.chat-scene--dev {
  grid-template-columns: 11rem minmax(0, 1fr) 20rem;
}

.chat-scene__sidebar {
  padding: 0.75rem 0.75rem 0.75rem 1rem;
  border-right: 1px solid var(--color-line);
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
  overflow: hidden;
}

.chat-scene__new-link {
  border: none;
  background: none;
  padding: 0.125rem 0;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  text-decoration: underline;
  text-underline-offset: 3px;
  text-align: left;
  cursor: pointer;
}

.chat-scene__new-link:hover {
  color: var(--color-text-primary);
}

.chat-scene__main {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
}

.chat-scene__bar {
  display: flex;
  align-items: center;
  padding: 0.5rem 1.25rem;
  border-bottom: 1px solid var(--color-line);
}

.chat-scene__empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem;
  gap: 0.5rem;
}

.chat-scene__empty-title {
  font-family: var(--font-diary);
  font-size: 1rem;
  color: var(--color-text-primary);
}

.chat-scene__empty-desc {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
}

.chat-scene__empty-link {
  margin-top: 0.75rem;
  border: none;
  background: none;
  padding: 0.25rem 0;
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  text-decoration: underline;
  text-underline-offset: 3px;
  cursor: pointer;
}

.chat-scene__empty-link:hover {
  color: var(--color-text-primary);
}

.chat-scene__messages {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  padding: 0.5rem 1rem 1rem;
}

/* 书信流：居中 40rem 纸面，细线日期小字分日 */
.letter-flow {
  width: min(40rem, 100%);
  margin: 0 auto;
  padding: 0 1.25rem;
  display: flex;
  flex-direction: column;
}

.letter-flow__divider {
  margin: 0.875rem 0 0.125rem;
  text-align: center;
  font-size: 0.6875rem;
  letter-spacing: 0.08em;
  color: var(--color-text-faint);
}

.chat-scene__composer {
  border-top: 1px solid var(--color-line);
  padding: 0.5rem 1.25rem 0.875rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.chat-scene__composer-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.chat-scene__composer-ink {
  flex-shrink: 0;
}

/* 进行中的信：与已落定的信同一版式，落款夜记、末尾研墨 */
.writing-letter {
  padding: 0.875rem 0 0.75rem;
  border-top: 1px solid var(--color-line);
}

.writing-letter__head {
  display: flex;
  align-items: baseline;
  font-size: 0.6875rem;
}

.writing-letter__signature {
  font-family: var(--font-diary);
  font-size: 0.8125rem;
  color: var(--color-text-primary);
}

.writing-letter__body {
  margin: 0.375rem 0 0;
  font-family: var(--font-diary);
  font-size: 0.9375rem;
  line-height: 1.95;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--color-text-primary);
}

.writing-letter__status {
  margin: 0.5rem 0 0;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
}

.chat-scene__dev {
  border-left: 1px solid var(--color-line);
  overflow: hidden;
}

.confirm-overlay {
  position: fixed;
  inset: 0;
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.35);
  backdrop-filter: blur(4px);
}

.confirm-dialog {
  width: min(20rem, calc(100vw - 2rem));
  padding: 1.5rem;
  border-radius: var(--radius-outer);
  border: 1px solid var(--color-border);
  background: var(--color-bg-elevated);
  text-align: center;
}

.confirm-dialog__title {
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 0.375rem;
}

.confirm-dialog__desc {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  margin-bottom: 1rem;
}

.confirm-dialog__actions {
  display: flex;
  justify-content: center;
  gap: 0.75rem;
}

.confirm-dialog__btn {
  padding: 0.4375rem 1rem;
  border-radius: 0.5rem;
  border: 1px solid var(--color-border);
  font-size: 0.8125rem;
  cursor: pointer;
}

.confirm-dialog__btn--cancel {
  background: var(--color-bg-elevated);
  color: var(--color-text-secondary);
}

.confirm-dialog__btn--danger {
  background: var(--color-danger);
  border-color: var(--color-danger);
  color: #fff;
  font-weight: 600;
}
</style>
