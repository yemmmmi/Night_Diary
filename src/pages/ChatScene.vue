<script setup lang="ts">
import { nextTick, onActivated, onMounted, ref, watch } from 'vue'
import { chatCopy } from '@/shared/copy/chat'
import { useChatStore } from '@/stores/chat'
import { useSettingsStore } from '@/stores/settings'
import { useCardStore } from '@/stores/card'
import ConversationList from '@/features/chat/ConversationList.vue'
import ChatMessage from '@/features/chat/ChatMessage.vue'
import ChatInput from '@/features/chat/ChatInput.vue'
import ReferencePanel from '@/features/chat/ReferencePanel.vue'
import OutputPanel from '@/features/chat/OutputPanel.vue'

defineOptions({ name: 'ChatScene' })

const chatStore = useChatStore()
const settings = useSettingsStore()
settings.load()
const cardStore = useCardStore()

const messagesEl = ref<HTMLElement | null>(null)
const showDeleteConfirm = ref(false)
const pendingDeleteId = ref<string | null>(null)
const cardSummary = ref<string | null>(null)
const cardGenerating = ref(false)

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) {
      messagesEl.value.scrollTop = messagesEl.value.scrollHeight
    }
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
  const ok = await chatStore.send(text)
  if (ok) scrollToBottom()
}

async function onGenerateCard() {
  cardGenerating.value = true
  const result = await chatStore.generateCard()
  if (result) {
    cardSummary.value = result.event_summary
  }
  cardGenerating.value = false
}

const dateDividers = (() => {
  const messages = chatStore.messages
  if (messages.length === 0) return []
  const dividers: { date: string; index: number }[] = []
  let currentDate = ''
  for (let i = 0; i < messages.length; i++) {
    const d = messages[i].created_at.slice(0, 10)
    if (d !== currentDate) {
      currentDate = d
      dividers.push({ date: d, index: i })
    }
  }
  return dividers.map((d) => ({
    ...d,
    key: `div-${d.date}`,
    totalBefore: d.index + dividers.filter((x) => x.date <= d.date).length,
  }))
})()

onMounted(async () => {
  await chatStore.loadConversations()
})

onActivated(async () => {
  await chatStore.loadConversations()
  if (chatStore.activeConversationId) {
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
        <p class="chat-scene__empty-title">{{ chatCopy.emptyTitle }}</p>
        <p class="chat-scene__empty-desc">{{ chatCopy.emptyDesc }}</p>
        <button type="button" class="chat-scene__new-btn chat-scene__new-btn--large" @click="onNewConversation">
          + {{ chatCopy.newConversation }}
        </button>
      </div>

      <!-- Messages -->
      <template v-else>
        <div ref="messagesEl" class="chat-scene__messages">
          <template v-for="(divider, di) in dateDividers" :key="divider.key">
            <p class="chat-scene__divider">{{ chatCopy.dateDivider(divider.date) }}</p>
            <ChatMessage
              v-for="msg in chatStore.messages.slice(divider.index, di + 1 < dateDividers.length ? dateDividers[di + 1].index : undefined)"
              :key="msg.id"
              :message="msg"
            />
          </template>

          <template v-if="dateDividers.length === 0 && chatStore.messages.length > 0">
            <ChatMessage
              v-for="msg in chatStore.messages"
              :key="msg.id"
              :message="msg"
            />
          </template>
        </div>

        <ChatInput :disabled="chatStore.sending" @send="onSend" />
      </template>
    </section>

    <!-- Right: reference + output + skill -->
    <aside class="chat-scene__aside">
      <div class="chat-scene__aside-scroll">
        <ReferencePanel
          :recent-diary-summary="null"
          :episodic-memories="[]"
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

.chat-scene__divider {
  text-align: center;
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
  margin: 0.5rem 0;
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
