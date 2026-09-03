<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PhArrowLeft } from '@phosphor-icons/vue'

import DiaryEditor from '@/features/diary/DiaryEditor.vue'
import CardDiaryPromptPanel from '@/features/diary/CardDiaryPromptPanel.vue'
import EmotionStamp from '@/shared/components/EmotionStamp.vue'
import GameButton from '@/shared/components/GameButton.vue'
import GlassPanel from '@/shared/components/GlassPanel.vue'
import { cardCopy } from '@/shared/copy/card'
import { diarySceneCopy as copy } from '@/shared/copy/diaryScene'
import { useDiaryStore } from '@/stores/diary'
import { useCardStore } from '@/stores/card'
import { findCardForDiary } from '@/shared/utils/cardFormat'
import { formatApiError } from '@/shared/utils/apiError'
import { countWordUnits, toIsoDate } from '@/shared/utils/diaryFormat'
import { buildDiaryMarkdown, diaryExportFilename } from '@/shared/utils/markdownExport'
import { useSettingsStore } from '@/stores/settings'
import DevPipelinePanel from '@/features/dev/DevPipelinePanel.vue'

function parseQueryDate(raw: unknown): string | null {
  if (typeof raw !== 'string' || !raw.trim()) return null
  if (!/^\d{4}-\d{2}-\d{2}$/.test(raw)) return null
  const parsed = new Date(`${raw}T00:00:00`)
  if (Number.isNaN(parsed.getTime())) return null
  return raw
}

const route = useRoute()
const router = useRouter()
const diaryStore = useDiaryStore()
const cardStore = useCardStore()
const settings = useSettingsStore()

const content = ref('')
const loadError = ref<string | null>(null)
const actionError = ref<string | null>(null)
const saveState = ref<'idle' | 'saving' | 'saved' | 'error'>('idle')
const showDeleteConfirm = ref(false)

const diaryId = computed(() => {
  const raw = route.params.id
  if (typeof raw === 'string' && raw.trim()) {
    const parsed = Number(raw)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
})

const isEditing = computed(() => diaryId.value != null)
const hasContent = computed(() => content.value.trim().length > 0)
const wordCount = computed(() => countWordUnits(content.value))
const showWritingHint = computed(() => !isEditing.value && !hasContent.value)

const linkedCard = computed(() => {
  if (!diaryId.value) return null
  return findCardForDiary(cardStore.cards, diaryId.value)
})

const isCardDiary = computed(() => linkedCard.value != null)

const emotions = computed<string[]>(() => {
  const card = linkedCard.value
  if (!card) return []
  if (card.emotions && card.emotions.length > 0) return card.emotions.filter(Boolean)
  return card.emotion ? [card.emotion] : []
})

const editorPlaceholder = computed(() => {
  if (isCardDiary.value) return cardCopy.cardDiaryPlaceholder
  if (showWritingHint.value) return copy.placeholderNew
  return copy.placeholderContinue
})

const targetDate = computed(() => {
  if (isEditing.value && diaryStore.currentEntry?.date) {
    return diaryStore.currentEntry.date
  }
  return parseQueryDate(route.query.date)
})

const dateLabel = computed(() => {
  const iso = targetDate.value
  if (iso) {
    const date = new Date(`${iso}T00:00:00`)
    return date.toLocaleDateString('zh-CN', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      weekday: 'long',
    })
  }
  return new Date().toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    weekday: 'long',
  })
})

const canSave = computed(() => {
  if (diaryStore.saving) return false
  if (isCardDiary.value && isEditing.value) return true
  return hasContent.value
})

const saveLabel = computed(() => (diaryStore.saving ? copy.saving : copy.save))

let saveStateTimer: ReturnType<typeof setTimeout> | null = null

function setSaveState(state: 'idle' | 'saving' | 'saved' | 'error') {
  saveState.value = state
  if (saveStateTimer) clearTimeout(saveStateTimer)
  if (state === 'saved') {
    saveStateTimer = setTimeout(() => {
      saveState.value = 'idle'
    }, 2000)
  }
}

async function loadEntry() {
  loadError.value = null
  if (!diaryId.value) {
    diaryStore.clearCurrent()
    content.value = ''
    saveState.value = 'idle'
    return
  }

  try {
    const entry = await diaryStore.fetchEntry(diaryId.value)
    content.value = entry.content ?? ''
    saveState.value = 'idle'
  } catch (err) {
    loadError.value = formatApiError(err, copy.loadFailed)
  }
}

async function persist(showFeedback = true) {
  const trimmed = content.value.trim()
  if (!trimmed && !isCardDiary.value) return

  setSaveState('saving')
  try {
    if (isEditing.value && diaryId.value) {
      await diaryStore.saveEntry(diaryId.value, {
        content: trimmed,
      })
      if (showFeedback) setSaveState('saved')
      else setSaveState('idle')
      return
    }

    if (!trimmed) return

    const created = await diaryStore.createEntry({
      content: trimmed,
      date: targetDate.value,
    })
    setSaveState('saved')
    await router.replace(`/write/${created.id}`)
  } catch {
    setSaveState('error')
  }
}

async function onAutosave(value: string) {
  if (!value.trim() && !isCardDiary.value) return
  if (!isEditing.value) return
  await persist(false)
}

async function onSaveClick() {
  await persist(true)
}

function exportMarkdown() {
  const iso = targetDate.value ?? toIsoDate(new Date())
  try {
    const md = buildDiaryMarkdown({ date: iso, content: content.value, emotions: emotions.value })
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = diaryExportFilename(iso)
    anchor.click()
    URL.revokeObjectURL(url)
  } catch {
    actionError.value = copy.exportFailed
  }
}

function confirmDelete() {
  showDeleteConfirm.value = true
}

async function executeDelete() {
  if (!diaryId.value) return
  showDeleteConfirm.value = false
  actionError.value = null
  try {
    await diaryStore.removeEntry(diaryId.value)
    await router.push('/timeline')
  } catch (err) {
    actionError.value = formatApiError(err, copy.deleteFailed)
    setSaveState('error')
  }
}

function close() {
  router.push('/timeline')
}

watch(
  () => route.fullPath,
  () => {
    void loadEntry()
  },
)

onMounted(async () => {
  await cardStore.loadCards()
  await loadEntry()
})
</script>

<template>
  <main class="diary-scene">
    <div class="diary-sheet diary-sheet--enter">
      <header class="diary-sheet__bar">
        <button type="button" class="diary-sheet__close" data-testid="diary-close" @click="close">
          <PhArrowLeft :size="15" />
          {{ copy.close }}
        </button>

        <p class="diary-sheet__date font-serif" data-testid="diary-date">{{ dateLabel }}</p>

        <GameButton
          variant="primary"
          data-testid="diary-save"
          :disabled="!canSave"
          @click="onSaveClick"
        >
          {{ saveLabel }}
        </GameButton>
      </header>

      <p v-if="loadError" class="diary-sheet__error">{{ loadError }}</p>
      <p v-if="actionError" class="diary-sheet__error">{{ actionError }}</p>
      <p v-else-if="diaryStore.error" class="diary-sheet__error">{{ diaryStore.error }}</p>

      <CardDiaryPromptPanel v-if="linkedCard && !loadError" :card="linkedCard" />

      <div v-if="!loadError" class="diary-sheet__body">
        <DiaryEditor v-model="content" :placeholder="editorPlaceholder" @autosave="onAutosave" />
      </div>

      <div v-if="emotions.length" class="diary-sheet__stamps">
        <EmotionStamp :emotions="emotions" />
      </div>

      <footer class="diary-sheet__foot">
        <div class="diary-sheet__links">
          <button
            v-if="isEditing"
            type="button"
            class="diary-sheet__link"
            data-testid="diary-export"
            @click="exportMarkdown"
          >
            {{ copy.exportMarkdown }}
          </button>
          <button
            v-if="isEditing"
            type="button"
            class="diary-sheet__link diary-sheet__link--danger"
            data-testid="diary-delete"
            @click="confirmDelete"
          >
            {{ copy.deleteEntry }}
          </button>
        </div>
        <span v-if="wordCount > 0" class="diary-sheet__word-count">
          {{ wordCount }} {{ copy.wordUnit }}
        </span>
        <span class="diary-sheet__save-dot" :class="`diary-sheet__save-dot--${saveState}`" />
      </footer>
    </div>

    <aside v-if="settings.developerMode" class="diary-scene__dev-panel">
      <DevPipelinePanel />
    </aside>

    <Teleport to="body">
      <div v-if="showDeleteConfirm" class="confirm-overlay" @click.self="showDeleteConfirm = false">
        <GlassPanel elevated class="confirm-dialog">
          <p class="confirm-dialog__title">{{ copy.confirmDeleteTitle }}</p>
          <p class="confirm-dialog__desc">{{ copy.confirmDeleteDesc }}</p>
          <div class="confirm-dialog__actions">
            <GameButton variant="secondary" @click="showDeleteConfirm = false">
              {{ copy.cancel }}
            </GameButton>
            <GameButton variant="primary" class="confirm-dialog__danger-btn" @click="executeDelete">
              {{ copy.confirmDelete }}
            </GameButton>
          </div>
        </GlassPanel>
      </div>
    </Teleport>
  </main>
</template>

<style scoped>
.diary-scene {
  min-height: calc(100vh - 2.5rem);
  padding: 0.75rem;
  display: flex;
  justify-content: center;
  gap: 0.75rem;
}

/* 稿纸是页面本身：纸白底、主栏宽居中、不用 hairline 包边 */
.diary-sheet {
  width: min(42rem, 100%);
  min-height: calc(100vh - 4rem);
  background: var(--color-diary-surface);
  padding: 0.5rem 1.5rem 1.25rem;
  display: flex;
  flex-direction: column;
}

.diary-sheet--enter {
  animation: sheet-land 450ms var(--ease-out-quart, cubic-bezier(0.25, 1, 0.5, 1)) both;
}

@keyframes sheet-land {
  from {
    opacity: 0;
    transform: translateY(16px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (prefers-reduced-motion: reduce) {
  .diary-sheet--enter {
    animation: none;
  }
}

.diary-sheet__bar {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 0.75rem;
  padding-bottom: 0.625rem;
  margin-bottom: 1rem;
  border-bottom: 1px solid var(--color-border);
}

.diary-sheet__close {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  background: none;
  border: none;
  padding: 0;
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  cursor: pointer;
}
.diary-sheet__close:hover {
  color: var(--color-text-primary);
}

.diary-sheet__date {
  text-align: center;
  font-size: 0.9375rem;
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.diary-sheet__body {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.diary-sheet__body :deep(.diary-editor__input) {
  font-size: 1.05rem;
  line-height: 2.15;
}

.diary-sheet__stamps {
  display: flex;
  justify-content: flex-end;
  margin-top: 1.5rem;
}

.diary-sheet__error {
  color: var(--color-danger);
  font-size: 0.875rem;
}

.diary-sheet__foot {
  margin-top: 1.25rem;
  padding-top: 0.625rem;
  border-top: 1px solid var(--color-border);
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

.diary-sheet__links {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-right: auto;
}

.diary-sheet__link {
  background: none;
  border: none;
  padding: 0;
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  text-decoration: underline;
  text-underline-offset: 3px;
  cursor: pointer;
}
.diary-sheet__link:hover {
  color: var(--color-text-primary);
}
.diary-sheet__link--danger {
  color: var(--color-danger);
  text-decoration: none;
}
.diary-sheet__link--danger:hover {
  color: var(--color-danger);
  opacity: 0.8;
}

.diary-sheet__word-count {
  opacity: 0.7;
}

.diary-sheet__save-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: transparent;
  transition: background-color var(--motion-duration) var(--motion-ease);
}
.diary-sheet__save-dot--idle {
  background: transparent;
}
.diary-sheet__save-dot--saving {
  background: color-mix(in srgb, var(--color-text-secondary) 50%, transparent);
}
.diary-sheet__save-dot--saved {
  background: var(--color-success);
}
.diary-sheet__save-dot--error {
  background: var(--color-danger);
}

.diary-scene__dev-panel {
  width: 320px;
  flex-shrink: 0;
  max-height: calc(100vh - 4rem);
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-outer);
  overflow: hidden;
}

.confirm-overlay {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.35);
  backdrop-filter: blur(4px);
}
.confirm-dialog {
  width: min(20rem, calc(100vw - 2rem));
  padding: 1.5rem;
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
.confirm-dialog__danger-btn {
  background: var(--color-danger) !important;
  color: #fff !important;
  box-shadow: 0 4px 14px color-mix(in srgb, var(--color-danger) 35%, transparent) !important;
}
.confirm-dialog__danger-btn:hover {
  opacity: 0.9;
}
</style>
