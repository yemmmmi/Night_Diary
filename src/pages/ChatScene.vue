<script setup lang="ts">
import { computed, nextTick, onActivated, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { chatCopy, type DiaryReferenceItem } from '@/shared/copy/chat'
import { listDiaryEntries, type DiaryEntry } from '@/shared/api/diary'
import { listCards, type MemoryCard } from '@/shared/api/card'
import { listEpisodic } from '@/shared/api/memory'
import { useChatStore } from '@/stores/chat'
import { useSettingsStore } from '@/stores/settings'
import { diaryEntrySummary } from '@/shared/utils/diaryFormat'
import ConversationList from '@/features/chat/ConversationList.vue'
import ChatMessage from '@/features/chat/ChatMessage.vue'
import ChatInput from '@/features/chat/ChatInput.vue'
import DiaryReferencePicker from '@/features/chat/DiaryReferencePicker.vue'
import ReferencePanel from '@/features/chat/ReferencePanel.vue'
import OutputPanel from '@/features/chat/OutputPanel.vue'
import AITypingIndicator from '@/shared/components/AITypingIndicator.vue'

defineOptions({ name: 'ChatScene' })

const route = useRoute()
const chatStore = useChatStore()
const settings = useSettingsStore()
settings.load()

const messagesEl = ref<HTMLElement | null>(null)
const showDeleteConfirm = ref(false)
const pendingDeleteId = ref<string | null>(null)
const cardSummary = ref<string | null>(null)
const cardGenerating = ref(false)
const diaryCatalog = ref<DiaryEntry[]>([])
const referenceCards = ref<MemoryCard[]>([])
const episodicMemories = ref<string[]>([])

function toReferenceItem(entry: DiaryEntry): DiaryReferenceItem {
  return {
    id: entry.id,
    date: entry.date,
    summary: diaryEntrySummary(entry, referenceCards.value, 48),
  }
}

const diaryLabelMap = computed(() => {
  const map: Record<number, string> = {}
  for (const entry of diaryCatalog.value) {
    map[entry.id] = diaryEntrySummary(entry, referenceCards.value, 20)
  }
  return map
})

const pinnedDiaries = computed(() =>
  chatStore.pinnedDiaryIds
    .map((id) => diaryCatalog.value.find((entry) => entry.id === id))
    .filter((entry): entry is DiaryEntry => entry != null)
    .map(toReferenceItem),
)

const lastAssistantMessage = computed(() =>
  [...chatStore.messages].reverse().find((msg) => msg.role === 'assistant') ?? null,
)

const retrievedDiaries = computed(() => {
  const ids = lastAssistantMessage.value?.retrieved_diary_ids ?? []
  const pinned = new Set(chatStore.pinnedDiaryIds)
  return ids
    .filter((id) => !pinned.has(id))
    .map((id) => diaryCatalog.value.find((entry) => entry.id === id))
    .filter((entry): entry is DiaryEntry => entry != null)
    .map(toReferenceItem)
})

async function loadReferenceData() {
  try {
    const [diaries, cards, episodic] = await Promise.all([
      listDiaryEntries({ limit: 50 }),
      listCards(),
      listEpisodic(),
    ])
    diaryCatalog.value = diaries
    referenceCards.value = cards
    episodicMemories.value = episodic.slice(0, 3).map((entry) => `[${entry.emotion}] ${entry.event}`)
  } catch {
    diaryCatalog.value = []
    referenceCards.value = []
    episodicMemories.value = []
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
  pendingUserText.value = text
  scrollToBottom()

  const ok = await chatStore.send(text)
  if (ok) {
    pendingUserText.value = null
  }
  scrollToBottom()
}

async function onGenerateCard() {
  cardGenerating.value = true
  const result = await chatStore.generateCard()
  if (result) {
    cardSummary.value = result.event_summary
  }
  cardGenerating.value = false
}

const pendingUserText = ref<string | null>(null)

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

watch(
  () => chatStore.activeConversationId,
  () => { cardSummary.value = null },
)
</script>

<template>
  <div class="chat-scene">
    <!-- Left: conversation list -->
    <aside class="chat-scene__sidebar">
      <button type="button" class="chat-scene__new-btn" @click="onNewConversation">
        + {{ chatCopy.newConversation }}
      </button>
      <ConversationList
        :conversations="chatStore.conversations"
        :active-id="chatStore.activeConversationId"
        @select="onSelectConversation"
        @delete="onAskDelete"
      />
    </aside>

    <!-- Center: messages + input -->
    <section class="chat-scene__main">
      <!-- Empty state -->
      <div v-if="!chatStore.activeConversationId" class="chat-scene__empty">
        <p class="chat-scene__empty-title">{{ chatCopy.emptyTitle(settings.nickname) }}</p>
        <p class="chat-scene__empty-desc">{{ chatCopy.emptyDesc(settings.nickname) }}</p>
        <button type="button" class="chat-scene__new-btn chat-scene__new-btn--large" @click="onNewConversation">
          + {{ chatCopy.newConversation }}
        </button>
      </div>

      <!-- Messages -->
      <template v-else>
        <div ref="messagesEl" class="chat-scene__messages">
          <template v-for="item in messageTimeline" :key="item.key">
            <p v-if="item.kind === 'divider'" class="chat-scene__divider">
              {{ chatCopy.dateDivider(item.date) }}
            </p>
            <ChatMessage
              v-else
              :message="item.message"
              :diary-labels="diaryLabelMap"
            />
          </template>

          <div v-if="chatStore.sending" class="chat-scene__typing">
            <AITypingIndicator :label="chatCopy.thinkingLabel" />
          </div>
        </div>

        <DiaryReferencePicker
          v-model="chatStore.pinnedDiaryIds"
          :entries="diaryCatalog"
          :cards="referenceCards"
          class="chat-scene__picker"
        />
        <ChatInput :disabled="chatStore.sending" @send="onSend" />
      </template>
    </section>

    <!-- Right: reference + output + skill -->
    <aside class="chat-scene__aside">
      <div class="chat-scene__aside-scroll">
        <ReferencePanel
          :pinned-diaries="pinnedDiaries"
          :retrieved-diaries="retrievedDiaries"
          :episodic-memories="episodicMemories"
          :loading="chatStore.loading"
        />
        <hr class="chat-scene__aside-divider" />
        <OutputPanel
          :card-summary="cardSummary"
          :generating="cardGenerating"
          :has-cards="false"
          @generate-card="onGenerateCard"
        />
        <hr class="chat-scene__aside-divider" />
        <section class="chat-scene__skill-panel">
          <p class="chat-scene__skill-placeholder">{{ chatCopy.skillPlaceholder }}</p>
        </section>
      </div>
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
  grid-template-columns: 12rem 1fr 16rem;
  /* titlebar 2.5rem + nav tabs ~3rem + app-shell frameless padding 2.5rem */
  height: calc(100dvh - 8rem);
  overflow: hidden;
  box-sizing: border-box;
}

.chat-scene__sidebar {
  padding: 0.75rem;
  border-right: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  overflow: hidden;
}

.chat-scene__new-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.4375rem 0.75rem;
  border: 1px dashed var(--color-border);
  border-radius: 0.5rem;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 0.75rem;
  cursor: pointer;
  transition: border-color var(--motion-duration) var(--motion-ease);
}

.chat-scene__new-btn:hover {
  border-color: var(--color-accent-muted);
  color: var(--color-text-primary);
}

.chat-scene__main {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
}

.chat-scene__empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem;
  gap: 0.5rem;
  color: var(--color-text-secondary);
  font-size: 0.875rem;
}

.chat-scene__empty-title {
  font-size: 1rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.chat-scene__new-btn--large {
  margin-top: 0.75rem;
  padding: 0.5rem 1rem;
  font-size: 0.8125rem;
}

.chat-scene__messages {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 1rem;
  overflow-y: auto;
  min-height: 0;
}

.chat-scene__picker {
  padding: 0 1rem 0.75rem;
  border-top: 1px solid var(--color-border);
}

.chat-scene__divider {
  text-align: center;
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
  margin: 0.5rem 0;
}

.chat-scene__typing {
  align-self: flex-start;
  padding: 0.25rem 0.5rem;
}

.chat-scene__aside {
  border-left: 1px solid var(--color-border);
  overflow: hidden;
}

.chat-scene__aside-scroll {
  padding: 0.75rem;
  height: 100%;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.chat-scene__aside-divider {
  border: none;
  border-top: 1px solid var(--color-border);
  margin: 0.75rem 0;
}

.chat-scene__skill-panel {
  display: flex;
  flex-direction: column;
}

.chat-scene__skill-placeholder {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  opacity: 0.5;
  text-align: center;
  padding: 1rem 0;
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
