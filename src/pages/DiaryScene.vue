<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PhArrowLeft, PhDotsThree } from '@phosphor-icons/vue'

import DiaryEditor from '@/features/diary/DiaryEditor.vue'
import GameButton from '@/shared/components/GameButton.vue'
import GlassPanel from '@/shared/components/GlassPanel.vue'
import { listTags, type Tag } from '@/shared/api/tags'
import { useDiaryStore } from '@/stores/diary'
import { countWordUnits, diaryStatus } from '@/shared/utils/diaryFormat'

const route = useRoute()
const router = useRouter()
const diaryStore = useDiaryStore()

const content = ref('')
const tagIds = ref<number[]>([])
const tags = ref<Tag[]>([])
const loadError = ref<string | null>(null)
const saveState = ref<'idle' | 'saving' | 'saved' | 'error'>('idle')
const showDeleteConfirm = ref(false)
const showMoreMenu = ref(false)
const menuRef = ref<HTMLElement | null>(null)

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

const editorPlaceholder = computed(() =>
  showWritingHint.value
    ? '今天发生了什么？不用修饰，说你想说的'
    : '写下此刻的想法…',
)

const dateLabel = computed(() => {
  const entryDate = diaryStore.currentEntry?.date
  if (entryDate) {
    const date = new Date(`${entryDate}T00:00:00`)
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

const canSave = computed(() => hasContent.value && !diaryStore.saving)

const entryStatus = computed(() =>
  diaryStore.currentEntry ? diaryStatus(diaryStore.currentEntry) : 'draft',
)

const showAnalysisAction = computed(
  () => isEditing.value && hasContent.value && entryStatus.value !== 'draft',
)

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

async function loadTags() {
  try {
    tags.value = await listTags()
  } catch {
    tags.value = []
  }
}

async function loadEntry() {
  loadError.value = null
  if (!diaryId.value) {
    diaryStore.clearCurrent()
    content.value = ''
    tagIds.value = []
    saveState.value = 'idle'
    return
  }

  try {
    const entry = await diaryStore.fetchEntry(diaryId.value)
    content.value = entry.content ?? ''
    tagIds.value = entry.tags.map((tag) => tag.id)
    saveState.value = 'idle'
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : '加载失败'
  }
}

async function persist(showFeedback = true) {
  const trimmed = content.value.trim()
  if (!trimmed) return

  setSaveState('saving')
  try {
    if (isEditing.value && diaryId.value) {
      await diaryStore.saveEntry(diaryId.value, {
        content: trimmed,
        tag_ids: tagIds.value,
      })
      if (showFeedback) setSaveState('saved')
      else setSaveState('idle')
      return
    }

    const created = await diaryStore.createEntry({
      content: trimmed,
      tag_ids: tagIds.value,
    })
    setSaveState('saved')
    await router.replace(`/write/${created.id}`)
  } catch {
    setSaveState('error')
  }
}

async function onAutosave(value: string) {
  if (!value.trim()) return
  if (!isEditing.value) return
  await persist(false)
}

async function onSaveClick() {
  await persist(true)
}

function confirmDelete() {
  showDeleteConfirm.value = true
  showMoreMenu.value = false
}

async function executeDelete() {
  if (!diaryId.value) return
  showDeleteConfirm.value = false
  try {
    await diaryStore.removeEntry(diaryId.value)
    await router.push('/')
  } catch {
    setSaveState('error')
  }
}

function toggleMoreMenu() {
  showMoreMenu.value = !showMoreMenu.value
}

function closeMoreMenu(e: MouseEvent) {
  if (menuRef.value && !menuRef.value.contains(e.target as Node)) {
    showMoreMenu.value = false
  }
}

function goBack() {
  router.push('/')
}

function goToAnalysis() {
  if (!diaryId.value) return
  router.push(`/analysis/${diaryId.value}`)
}

watch(
  () => route.fullPath,
  () => {
    void loadEntry()
  },
)

watch(tagIds, async (value, oldValue) => {
  if (!isEditing.value || !diaryId.value) return
  if (value.join(',') === oldValue.join(',')) return
  await diaryStore.saveEntry(diaryId.value, { tag_ids: value })
})

onMounted(async () => {
  await loadTags()
  await loadEntry()
  document.addEventListener('click', closeMoreMenu)
})
</script>

<template>
  <main class="diary-scene">
    <div class="diary-scene__surface">
      <header class="diary-scene__header">
        <GameButton variant="ghost" @click="goBack">
          <PhArrowLeft :size="16" />
          返回
        </GameButton>

        <div class="diary-scene__meta">
          <p class="diary-scene__date">{{ dateLabel }}</p>
        </div>

        <div class="diary-scene__actions">
          <div v-if="isEditing" class="more-menu-wrapper" ref="menuRef">
            <GameButton variant="ghost" @click.stop="toggleMoreMenu">
              <PhDotsThree :size="16" />
            </GameButton>
            <div v-if="showMoreMenu" class="more-menu">
              <button type="button" class="more-menu__item more-menu__item--danger" @click="confirmDelete">
                删除日记
              </button>
            </div>
          </div>

          <GameButton variant="primary" :disabled="!canSave" @click="onSaveClick">
            {{ diaryStore.saving ? '保存中…' : '保存' }}
          </GameButton>
        </div>
      </header>

      <p v-if="loadError" class="diary-scene__error">{{ loadError }}</p>

      <DiaryEditor
        v-if="!loadError"
        v-model="content"
        v-model:tag-ids="tagIds"
        :tags="tags"
        :placeholder="editorPlaceholder"
        @autosave="onAutosave"
      />

      <footer class="diary-scene__footer">
        <span v-if="wordCount > 0" class="diary-scene__word-count">{{ wordCount }} 字</span>
        <GameButton
          v-if="showAnalysisAction"
          variant="secondary"
          class="diary-scene__analysis-btn"
          @click="goToAnalysis"
        >
          {{ diaryStore.currentEntry?.ai_ans?.trim() ? '查看 AI 回信' : '获取 AI 回信' }}
        </GameButton>
        <span class="diary-scene__save-dot" :class="`diary-scene__save-dot--${saveState}`" />
      </footer>
    </div>

    <!-- 删除确认对话框 -->
    <Teleport to="body">
      <div v-if="showDeleteConfirm" class="confirm-overlay" @click.self="showDeleteConfirm = false">
        <GlassPanel elevated class="confirm-dialog">
          <p class="confirm-dialog__title">确定删除这篇日记吗？</p>
          <p class="confirm-dialog__desc">删除后将无法恢复</p>
          <div class="confirm-dialog__actions">
            <GameButton variant="secondary" @click="showDeleteConfirm = false">取消</GameButton>
            <GameButton variant="primary" class="confirm-dialog__danger-btn" @click="executeDelete">
              确认删除
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

/* 更多菜单 */
.more-menu-wrapper {
  position: relative;
}
.more-menu {
  position: absolute;
  right: 0;
  top: 100%;
  margin-top: 0.25rem;
  min-width: 8rem;
  padding: 0.375rem;
  border-radius: 0.75rem;
  border: 1px solid var(--color-border);
  background: var(--color-bg-elevated);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
  z-index: 50;
}
.more-menu__item {
  width: 100%;
  text-align: left;
  background: none;
  border: none;
  padding: 0.5rem 0.75rem;
  border-radius: 0.5rem;
  font-size: 0.8125rem;
  color: var(--color-text-primary);
  cursor: pointer;
}
.more-menu__item:hover {
  background: var(--color-bg-elevated-2);
}
.more-menu__item--danger {
  color: var(--color-danger);
}

/* 错误 */
.diary-scene__error {
  color: var(--color-danger);
  font-size: 0.875rem;
}

/* 底部状态条 */
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

.diary-scene__analysis-btn {
  font-size: 0.8125rem;
}

/* 保存状态圆点 */
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

/* 删除确认弹窗 */
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