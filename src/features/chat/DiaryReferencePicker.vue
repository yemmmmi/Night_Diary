<script setup lang="ts">
import { computed, ref } from 'vue'

import type { DiaryEntry } from '@/shared/api/diary'
import type { MemoryCard } from '@/shared/api/card'
import { chatCopy } from '@/shared/copy/chat'
import { findCardForDiary } from '@/shared/utils/cardFormat'
import { diaryEntrySummary, diarySummary, toIsoDate } from '@/shared/utils/diaryFormat'
import { serverDateIso } from '@/shared/utils/timeFormat'

const props = withDefaults(
  defineProps<{
    modelValue: number[]
    cardModelValue?: string[]
    entries: DiaryEntry[]
    cards?: MemoryCard[]
    max?: number
    loading?: boolean
  }>(),
  {
    cardModelValue: () => [],
    cards: () => [],
    loading: false,
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: number[]]
  'update:cardModelValue': [value: string[]]
}>()

const open = ref(false)

const maxCount = computed(() => props.max ?? 3)
const selectedIds = computed(() => props.modelValue)
const selectedCardIds = computed(() => props.cardModelValue)

const entryById = computed(() => {
  const map = new Map<number, DiaryEntry>()
  for (const entry of props.entries) {
    map.set(entry.id, entry)
  }
  return map
})

function entryDateIso(entry: DiaryEntry): string {
  return entry.date ?? serverDateIso(entry.created_at)
}

function linkedCard(entry: DiaryEntry): MemoryCard | null {
  return findCardForDiary(props.cards, entry.id)
}

function isReferencable(entry: DiaryEntry): boolean {
  if (entry.content?.trim()) return true
  if (entry.reply?.trim()) return true
  if (entry.weather?.trim()) return true
  if (linkedCard(entry)?.event_summary?.trim()) return true
  return entryDateIso(entry) === toIsoDate(new Date())
}

function entryPreview(entry: DiaryEntry, maxLen = 36): string {
  if (entry.content?.trim()) return diarySummary(entry.content, maxLen)
  if (entry.weather?.trim()) return `天气：${entry.weather.trim()}`
  if (entry.reply?.trim()) return `回信：${diarySummary(entry.reply, Math.min(maxLen, 28))}`
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

/* 独立卡：未关联任何日记（diary_id == null）的卡片，卡片日记在日记区已可达 */
const standaloneCards = computed(() =>
  [...props.cards]
    .filter((card) => card.diary_id === null)
    .sort((a, b) => b.created_at.localeCompare(a.created_at)),
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

function toggleCard(cardId: string) {
  if (selectedCardIds.value.includes(cardId)) {
    emit(
      'update:cardModelValue',
      selectedCardIds.value.filter((id) => id !== cardId),
    )
    return
  }
  if (selectedCardIds.value.length >= maxCount.value) return
  emit('update:cardModelValue', [...selectedCardIds.value, cardId])
}

function removePin(id: number) {
  emit(
    'update:modelValue',
    selectedIds.value.filter((entryId) => entryId !== id),
  )
}

function removeCardPin(cardId: string) {
  emit(
    'update:cardModelValue',
    selectedCardIds.value.filter((id) => id !== cardId),
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

function cardChipLabel(card: MemoryCard): string {
  const summary = (card.event_summary ?? '').trim()
  if (summary) return diarySummary(summary, 16)
  return `${card.emotion}的卡片`
}

function cardDateLabel(card: MemoryCard): string {
  const iso = serverDateIso(card.created_at)
  const today = toIsoDate(new Date())
  if (iso === today) return '今天'
  return new Date(`${iso}T00:00:00`).toLocaleDateString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
  })
}

function cardById(cardId: string): MemoryCard | undefined {
  return standaloneCards.value.find((card) => card.card_id === cardId)
}

const bothSlotsFull = computed(
  () =>
    selectedIds.value.length >= maxCount.value &&
    selectedCardIds.value.length >= maxCount.value,
)
</script>

<template>
  <section class="diary-picker">
    <div class="diary-picker__selected">
      <button
        v-for="id in selectedIds"
        :key="`d-${id}`"
        type="button"
        class="diary-picker__chip diary-picker__chip--selected"
        :title="chatCopy.removePin"
        @click="removePin(id)"
      >
        {{ chipLabel(id) }}
        <span aria-hidden="true">×</span>
      </button>
      <button
        v-for="cardId in selectedCardIds"
        :key="`c-${cardId}`"
        type="button"
        class="diary-picker__chip diary-picker__chip--selected diary-picker__chip--card"
        data-testid="diary-picker__chip-card"
        :title="chatCopy.removeCardPin"
        @click="removeCardPin(cardId)"
      >
        {{ cardById(cardId) ? cardChipLabel(cardById(cardId)!) : '卡片' }}
        <span aria-hidden="true">×</span>
      </button>
      <button
        type="button"
        class="diary-picker__add"
        :class="{ 'is-open': open }"
        :disabled="bothSlotsFull"
        @click="open = !open"
      >
        + {{ chatCopy.pickDiary }}
      </button>
    </div>

    <div v-if="open" class="diary-picker__panel">
      <p class="diary-picker__hint">{{ chatCopy.pickDiaryHint }}</p>
      <p v-if="loading" class="diary-picker__empty">{{ chatCopy.noReference }}</p>
      <template v-else>
        <div v-if="availableDiaries.length" class="diary-picker__list">
          <button
            v-for="entry in availableDiaries"
            :key="entry.id"
            type="button"
            class="diary-picker__item"
            :class="{ 'is-selected': selectedIds.includes(entry.id) }"
            :aria-pressed="selectedIds.includes(entry.id)"
            data-testid="diary-picker__item"
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
        <p v-else class="diary-picker__empty">{{ chatCopy.pickDiaryEmpty }}</p>

        <template v-if="standaloneCards.length">
          <p class="diary-picker__section">{{ chatCopy.pickCardSection }}</p>
          <div class="diary-picker__list">
            <button
              v-for="card in standaloneCards"
              :key="card.card_id"
              type="button"
              class="diary-picker__item"
              :class="{ 'is-selected': selectedCardIds.includes(card.card_id) }"
              :aria-pressed="selectedCardIds.includes(card.card_id)"
              data-testid="diary-picker__card-item"
              @click="toggleCard(card.card_id)"
            >
              <span class="diary-picker__item-head">
                <span class="diary-picker__date">{{ cardDateLabel(card) }}</span>
                <span class="diary-picker__meta">{{ card.emotion }}</span>
              </span>
              <span class="diary-picker__summary">
                {{ (card.event_summary ?? '').trim() || chatCopy.pickCardHint }}
              </span>
            </button>
          </div>
        </template>
      </template>
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

/* 卡片 chip 以细体描边区分来源 */
.diary-picker__chip--card {
  border-style: dashed;
}

.diary-picker__section {
  margin: 0.125rem 0 0;
  font-size: 0.6875rem;
  letter-spacing: 0.06em;
  color: var(--color-text-faint);
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
