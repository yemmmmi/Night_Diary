<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PhArrowLeft } from '@phosphor-icons/vue'

import DiaryEditor from '@/features/diary/DiaryEditor.vue'
import CardDiaryPromptPanel from '@/features/diary/CardDiaryPromptPanel.vue'
import DiaryReplySection from '@/features/diary/DiaryReplySection.vue'
import GameButton from '@/shared/components/GameButton.vue'
import GlassPanel from '@/shared/components/GlassPanel.vue'
import { cardCopy } from '@/shared/copy/card'
import { diarySceneCopy as copy } from '@/shared/copy/diaryScene'
import { useDiaryStore } from '@/stores/diary'
import { useCardStore } from '@/stores/card'
import { useAnalysisStore } from '@/stores/analysis'
import { findCardForDiary } from '@/shared/utils/cardFormat'
import { formatApiError } from '@/shared/utils/apiError'
import { countWordUnits, diaryStatus } from '@/shared/utils/diaryFormat'

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
const analysisStore = useAnalysisStore()

const content = ref('')
const loadError = ref<string | null>(null)
const deleteError = ref<string | null>(null)
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

const entryStatus = computed(() =>
  diaryStore.currentEntry ? diaryStatus(diaryStore.currentEntry) : 'draft',
)

const showReplySection = computed(
  () => isEditing.value && diaryStore.currentEntry && entryStatus.value !== 'draft',
)

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

async function loadAnalysis() {
  if (!diaryId.value) {
    analysisStore.clear()
    return
  }
  try {
    await analysisStore.loadForDiary(diaryId.value)
  } catch {
    // 404 = no analysis yet
  }
}

async function loadEntry() {
  loadError.value = null
  if (!diaryId.value) {
    diaryStore.clearCurrent()
    analysisStore.clear()
    content.value = ''
    saveState.value = 'idle'
    return
  }

  try {
    const entry = await diaryStore.fetchEntry(diaryId.value)
    content.value = entry.content ?? ''
    saveState.value = 'idle'
    await loadAnalysis()
    await scrollToReplyIfNeeded()
  } catch (err) {
    loadError.value = formatApiError(err, copy.loadFailed)
  }
}

async function scrollToReplyIfNeeded() {
  if (route.hash !== '#reply') return
  await nextTick()
  document.getElementById('reply')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

async function onAnalysisRefreshed() {
  if (!diaryId.value) return
  await diaryStore.fetchEntry(diaryId.value)
  await loadAnalysis()
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

function confirmDelete() {
  showDeleteConfirm.value = true
}

async function executeDelete() {
  if (!diaryId.value) return
  showDeleteConfirm.value = false
  deleteError.value = null
  try {
    await diaryStore.removeEntry(diaryId.value)
    await router.push('/')
  } catch (err) {
    deleteError.value = formatApiError(err, copy.deleteFailed)
    setSaveState('error')
  }
}

function goBack() {
  router.push('/')
}

watch(
  () => route.fullPath,
  () => {
    void loadEntry()
  },
)

watch(
  () => route.hash,
  () => {
    void scrollToReplyIfNeeded()
  },
)

onMounted(async () => {
  await cardStore.loadCards()
  await loadEntry()
})
</script>

<template>
  <main class="diary-scene">
    <div class="diary-scene__surface">
      <header class="diary-scene__header">
        <GameButton variant="ghost" @click="goBack">
          <PhArrowLeft :size="16" />
          {{ copy.back }}
        </GameButton>

        <div class="diary-scene__meta">
          <p class="diary-scene__date">{{ dateLabel }}</p>
        </div>

        <div class="diary-scene__actions">
          <GameButton
            v-if="isEditing"
            variant="ghost"
            class="diary-scene__delete-btn"
            @click="confirmDelete"
          >
            {{ copy.deleteDiary }}
          </GameButton>

          <GameButton variant="primary" :disabled="!canSave" @click="onSaveClick">
            {{ saveLabel }}
          </GameButton>
        </div>
      </header>

      <p v-if="loadError" class="diary-scene__error">{{ loadError }}</p>
      <p v-if="deleteError" class="diary-scene__error">{{ deleteError }}</p>
      <p v-else-if="diaryStore.error" class="diary-scene__error">{{ diaryStore.error }}</p>

      <CardDiaryPromptPanel v-if="linkedCard && !loadError" :card="linkedCard" />

      <DiaryEditor
        v-if="!loadError"
        v-model="content"
        :placeholder="editorPlaceholder"
        @autosave="onAutosave"
      />

      <DiaryReplySection
        v-if="showReplySection && diaryId && diaryStore.currentEntry"
        :diary-id="diaryId"
        :entry="diaryStore.currentEntry"
        :analysis="analysisStore.current"
        :loading="analysisStore.loading"
        :triggering="analysisStore.triggering"
        @refreshed="onAnalysisRefreshed"
      />

      <footer class="diary-scene__footer">
        <span v-if="wordCount > 0" class="diary-scene__word-count">
          {{ wordCount }} {{ copy.wordUnit }}
        </span>
        <span class="diary-scene__save-dot" :class="`diary-scene__save-dot--${saveState}`" />
      </footer>
    </div>

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
}

.diary-scene__surface {
  width: min(48rem, 100%);
  min-height: calc(100vh - 4rem);
  background: var(--color-diary-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-outer);
  padding: 1rem 1.25rem 1.25rem;
  display: flex;
  flex-direction: column;
}

.diary-scene__header {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}

.diary-scene__meta {
  min-width: 0;
  text-align: center;
}
.diary-scene__date {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.diary-scene__actions {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  position: relative;
}

.diary-scene__delete-btn {
  font-size: 0.8125rem;
  color: var(--color-danger) !important;
  border-color: color-mix(in srgb, var(--color-danger) 35%, var(--color-border)) !important;
}

.diary-scene__error {
  color: var(--color-danger);
  font-size: 0.875rem;
}

.diary-scene__footer {
  margin-top: 0.75rem;
  padding-top: 0.5rem;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.5rem;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}
.diary-scene__word-count {
  opacity: 0.7;
  margin-right: auto;
}

.diary-scene__save-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: transparent;
  transition: background-color var(--motion-duration) var(--motion-ease);
}
.diary-scene__save-dot--idle {
  background: transparent;
}
.diary-scene__save-dot--saving {
  background: color-mix(in srgb, var(--color-text-secondary) 50%, transparent);
}
.diary-scene__save-dot--saved {
  background: var(--color-success);
}
.diary-scene__save-dot--error {
  background: var(--color-danger);
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
