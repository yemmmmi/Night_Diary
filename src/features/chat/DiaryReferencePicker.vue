<script setup lang="ts">
import { computed, ref } from 'vue'

import type { DiaryEntry } from '@/shared/api/diary'
import type { MemoryCard } from '@/shared/api/card'
import { chatCopy } from '@/shared/copy/chat'
import { findCardForDiary } from '@/shared/utils/cardFormat'
import { diaryEntrySummary, diarySummary, toIsoDate } from '@/shared/utils/diaryFormat'

const props = withDefaults(
  defineProps<{
    modelValue: number[]
    entries: DiaryEntry[]
    cards?: MemoryCard[]
    max?: number
    loading?: boolean
  }>(),
  {
    cards: () => [],
    loading: false,
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: number[]]
}>()

const open = ref(false)

const maxCount = computed(() => props.max ?? 3)
const selectedIds = computed(() => props.modelValue)

const entryById = computed(() => {
  const map = new Map<number, DiaryEntry>()
  for (const entry of props.entries) {
    map.set(entry.id, entry)
  }
  return map
})

function entryDateIso(entry: DiaryEntry): string {
  return entry.date ?? entry.created_at.slice(0, 10)
}

function linkedCard(entry: DiaryEntry): MemoryCard | null {
  return findCardForDiary(props.cards, entry.id)
}

function isReferencable(entry: DiaryEntry): boolean {
  if (entry.content?.trim()) return true
  if (entry.ai_ans?.trim()) return true
  if (entry.weather?.trim()) return true
  if (linkedCard(entry)?.event_summary?.trim()) return true
  return entryDateIso(entry) === toIsoDate(new Date())
}

function entryPreview(entry: DiaryEntry, maxLen = 36): string {
  if (entry.content?.trim()) return diarySummary(entry.content, maxLen)
  if (entry.weather?.trim()) return `天气：${entry.weather.trim()}`
  if (entry.ai_ans?.trim()) return `回信：${diarySummary(entry.ai_ans, Math.min(maxLen, 28))}`
  return diaryEntrySummary(entry, props.cards, maxLen)
}

const availableDiaries = computed(() =>
  [...props.entries]
    .filter(isReferencable)
    .sort((a, b) => {
      const dateCmp = entryDateIso(b).localeCompare(entryDateIso(a))
      if (dateCmp !== 0) return dateCmp
      return b.created_at.localeCompare(a.created_at)
    }),
)

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

function formatDateLabel(entry: DiaryEntry): string {
  const iso = entryDateIso(entry)
  const today = toIsoDate(new Date())
  if (iso === today) return '今天'
  return new Date(`${iso}T00:00:00`).toLocaleDateString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
  })
}

function chipLabel(id: number): string {
  const entry = entryById.value.get(id)
  return entry ? entryPreview(entry, 16) : `#${id}`
}
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
        {{ chipLabel(id) }}
        <span aria-hidden="true">×</span>
      </button>
      <button
        type="button"
        class="diary-picker__add"
        :class="{ 'is-open': open }"
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
      <div v-else class="diary-picker__list">
        <button
          v-for="entry in availableDiaries"
          :key="entry.id"
          type="button"
          class="diary-picker__item"
          :class="{ 'is-selected': selectedIds.includes(entry.id) }"
          :aria-pressed="selectedIds.includes(entry.id)"
          @click="toggleDiary(entry.id)"
        >
          <span class="diary-picker__item-head">
            <span class="diary-picker__date">{{ formatDateLabel(entry) }}</span>
            <span
              v-if="entry.weather?.trim()"
              class="diary-picker__meta"
            >
              {{ entry.weather.trim() }}
            </span>
          </span>
          <span class="diary-picker__summary">{{ entryPreview(entry) }}</span>
        </button>
      </div>
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
  padding: 0.25rem 0.625rem;
  border-radius: 999px;
  border: 1px solid var(--color-border);
  background: var(--color-bg-elevated);
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition:
    border-color var(--motion-duration) var(--motion-ease),
    background var(--motion-duration) var(--motion-ease),
    color var(--motion-duration) var(--motion-ease);
}

.diary-picker__add:hover:not(:disabled),
.diary-picker__add.is-open {
  border-color: color-mix(in srgb, var(--color-accent) 35%, var(--color-border));
  color: var(--color-text-primary);
}

.diary-picker__chip--selected {
  border-color: color-mix(in srgb, var(--color-accent) 45%, var(--color-border));
  background: color-mix(in srgb, var(--color-accent) 12%, var(--color-bg-elevated));
  color: var(--color-text-primary);
}

.diary-picker__panel {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  max-height: 14rem;
  overflow-y: auto;
  padding: 0.625rem;
  border: 1px solid var(--color-border);
  border-radius: 0.625rem;
  background: color-mix(in srgb, var(--color-bg-elevated) 80%, transparent);
}

.diary-picker__hint,
.diary-picker__empty {
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
}

.diary-picker__list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.diary-picker__item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.25rem;
  width: 100%;
  padding: 0.625rem 0.75rem;
  border-radius: 0.5rem;
  border: 1px solid var(--color-border);
  background: var(--color-bg-elevated);
  text-align: left;
  cursor: pointer;
  transition:
    border-color var(--motion-duration) var(--motion-ease),
    background var(--motion-duration) var(--motion-ease),
    box-shadow var(--motion-duration) var(--motion-ease);
}

.diary-picker__item:hover {
  border-color: color-mix(in srgb, var(--color-accent) 30%, var(--color-border));
  background: var(--color-bg-elevated-2);
}

.diary-picker__item.is-selected {
  border-color: color-mix(in srgb, var(--color-accent) 50%, var(--color-border));
  background: color-mix(in srgb, var(--color-accent) 10%, var(--color-bg-elevated));
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--color-accent) 20%, transparent);
}

.diary-picker__item-head {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  width: 100%;
}

.diary-picker__date {
  font-size: 0.6875rem;
  color: var(--color-accent);
  font-weight: 600;
}

.diary-picker__meta {
  font-size: 0.625rem;
  color: var(--color-text-secondary);
  padding: 0.0625rem 0.375rem;
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-text-secondary) 8%, transparent);
}

.diary-picker__summary {
  font-size: 0.8125rem;
  line-height: 1.45;
  color: var(--color-text-primary);
}
</style>
