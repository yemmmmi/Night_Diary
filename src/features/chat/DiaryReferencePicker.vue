<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { listDiaryEntries, type DiaryEntry } from '@/shared/api/diary'
import { chatCopy } from '@/shared/copy/chat'
import { diarySummary } from '@/shared/utils/diaryFormat'

const props = defineProps<{
  modelValue: number[]
  max?: number
}>()

const emit = defineEmits<{
  'update:modelValue': [value: number[]]
}>()

const diaries = ref<DiaryEntry[]>([])
const loading = ref(false)
const open = ref(false)

const maxCount = computed(() => props.max ?? 3)
const selectedIds = computed(() => props.modelValue)

const availableDiaries = computed(() =>
  diaries.value.filter((entry) => entry.content?.trim()),
)

async function loadDiaries() {
  loading.value = true
  try {
    diaries.value = await listDiaryEntries({ limit: 50 })
  } catch {
    diaries.value = []
  } finally {
    loading.value = false
  }
}

function toggleDiary(id: number) {
  if (selectedIds.value.includes(id)) {
    emit(
      'update:modelValue',
      selectedIds.value.filter((entryId) => entryId !== id),
    )
    return
  }
  if (selectedIds.value.length >= maxCount.value) return
  emit('update:modelValue', [...selectedIds.value, id])
}

function removePin(id: number) {
  emit(
    'update:modelValue',
    selectedIds.value.filter((entryId) => entryId !== id),
  )
}

function formatDate(date: string | null) {
  if (!date) return '未标注日期'
  return new Date(`${date}T00:00:00`).toLocaleDateString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
  })
}

onMounted(() => {
  void loadDiaries()
})
</script>

<template>
  <section class="diary-picker">
    <div class="diary-picker__selected">
      <button
        v-for="id in selectedIds"
        :key="id"
        type="button"
        class="diary-picker__chip diary-picker__chip--selected"
        :title="chatCopy.removePin"
        @click="removePin(id)"
      >
        #{{
          diaries.find((entry) => entry.id === id)
            ? diarySummary(diaries.find((entry) => entry.id === id)?.content, 16)
            : id
        }}
        <span aria-hidden="true">×</span>
      </button>
      <button
        type="button"
        class="diary-picker__add"
        :disabled="selectedIds.length >= maxCount"
        @click="open = !open"
      >
        + {{ chatCopy.pickDiary }}
      </button>
    </div>

    <div v-if="open" class="diary-picker__panel">
      <p class="diary-picker__hint">{{ chatCopy.pickDiaryHint }}</p>
      <p v-if="loading" class="diary-picker__empty">{{ chatCopy.noReference }}</p>
      <p v-else-if="availableDiaries.length === 0" class="diary-picker__empty">
        {{ chatCopy.pickDiaryEmpty }}
      </p>
      <button
        v-for="entry in availableDiaries"
        :key="entry.id"
        type="button"
        class="diary-picker__item"
        :class="{ 'is-selected': selectedIds.includes(entry.id) }"
        @click="toggleDiary(entry.id)"
      >
        <span class="diary-picker__date">{{ formatDate(entry.date) }}</span>
        <span class="diary-picker__summary">{{ diarySummary(entry.content, 36) }}</span>
      </button>
    </div>
  </section>
</template>

<style scoped>
.diary-picker {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.diary-picker__selected {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
}

.diary-picker__chip,
.diary-picker__add {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.5rem;
  border-radius: 999px;
  border: 1px solid var(--color-border);
  background: var(--color-bg-elevated);
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
  cursor: pointer;
}

.diary-picker__chip--selected {
  border-color: color-mix(in srgb, var(--color-accent) 40%, var(--color-border));
  color: var(--color-text-primary);
}

.diary-picker__panel {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  max-height: 10rem;
  overflow-y: auto;
  padding: 0.5rem;
  border: 1px solid var(--color-border);
  border-radius: 0.5rem;
  background: var(--color-bg-elevated);
}

.diary-picker__hint,
.diary-picker__empty {
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
}

.diary-picker__item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.125rem;
  padding: 0.375rem 0.5rem;
  border-radius: 0.375rem;
  border: 1px solid transparent;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.diary-picker__item.is-selected {
  border-color: color-mix(in srgb, var(--color-accent) 35%, var(--color-border));
  background: color-mix(in srgb, var(--color-accent) 10%, transparent);
}

.diary-picker__date {
  font-size: 0.625rem;
  color: var(--color-accent);
  font-weight: 600;
}

.diary-picker__summary {
  font-size: 0.75rem;
  color: var(--color-text-primary);
}
</style>
