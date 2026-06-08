<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PhArrowLeft, PhTrash } from '@phosphor-icons/vue'

import DiaryEditor from '@/features/diary/DiaryEditor.vue'
import GameButton from '@/shared/components/GameButton.vue'
import { listTags, type Tag } from '@/shared/api/tags'
import { useDiaryStore } from '@/stores/diary'
import { countWordUnits } from '@/shared/utils/diaryFormat'

const route = useRoute()
const router = useRouter()
const diaryStore = useDiaryStore()

const content = ref('')
const tagIds = ref<number[]>([])
const tags = ref<Tag[]>([])
const saveHint = ref<string | null>(null)
const loadError = ref<string | null>(null)

const diaryId = computed(() => {
  const raw = route.params.id
  if (typeof raw === 'string' && raw.trim()) {
    const parsed = Number(raw)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
})

const isEditing = computed(() => diaryId.value != null)

const wordCount = computed(() => countWordUnits(content.value))

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

const canSave = computed(() => content.value.trim().length > 0 && !diaryStore.saving)

let hintTimer: ReturnType<typeof setTimeout> | null = null

function showHint(message: string) {
  saveHint.value = message
  if (hintTimer) clearTimeout(hintTimer)
  hintTimer = setTimeout(() => {
    saveHint.value = null
  }, 2000)
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
    return
  }

  try {
    const entry = await diaryStore.fetchEntry(diaryId.value)
    content.value = entry.content ?? ''
    tagIds.value = entry.tags.map((tag) => tag.id)
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : '加载失败'
  }
}

async function persist(showMessage = true) {
  const trimmed = content.value.trim()
  if (!trimmed) return

  try {
    if (isEditing.value && diaryId.value) {
      await diaryStore.saveEntry(diaryId.value, {
        content: trimmed,
        tag_ids: tagIds.value,
      })
      if (showMessage) showHint('已保存')
      return
    }

    const created = await diaryStore.createEntry({
      content: trimmed,
      tag_ids: tagIds.value,
    })
    if (showMessage) showHint('已保存')
    await router.replace(`/write/${created.id}`)
  } catch {
    showHint('保存失败')
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

async function onDelete() {
  if (!diaryId.value) return
  if (!window.confirm('确定删除这篇日记吗？')) return

  try {
    await diaryStore.removeEntry(diaryId.value)
    await router.push('/')
  } catch {
    showHint('删除失败')
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

watch(tagIds, async (value, oldValue) => {
  if (!isEditing.value || !diaryId.value) return
  if (value.join(',') === oldValue.join(',')) return
  await diaryStore.saveEntry(diaryId.value, { tag_ids: value })
})

onMounted(async () => {
  await loadTags()
  await loadEntry()
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
          <p v-if="saveHint" class="diary-scene__hint">{{ saveHint }}</p>
        </div>

        <div class="diary-scene__actions">
          <GameButton v-if="isEditing" variant="ghost" @click="onDelete">
            <PhTrash :size="16" />
          </GameButton>
          <GameButton variant="primary" :disabled="!canSave" @click="onSaveClick">
            {{ diaryStore.saving ? '保存中…' : '保存' }}
          </GameButton>
        </div>
      </header>

      <p v-if="loadError" class="diary-scene__error">{{ loadError }}</p>

      <DiaryEditor
        v-else
        v-model="content"
        v-model:tag-ids="tagIds"
        :tags="tags"
        @autosave="onAutosave"
      />

      <footer class="diary-scene__footer">
        <span>{{ wordCount }} 字</span>
      </footer>
    </div>
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

.diary-scene__hint {
  margin-top: 0.125rem;
  font-size: 0.75rem;
  color: var(--color-success);
}

.diary-scene__actions {
  display: flex;
  align-items: center;
  gap: 0.375rem;
}

.diary-scene__error {
  color: var(--color-danger);
  font-size: 0.875rem;
}

.diary-scene__footer {
  margin-top: 0.75rem;
  padding-top: 0.625rem;
  border-top: 1px solid var(--color-border);
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}
</style>
