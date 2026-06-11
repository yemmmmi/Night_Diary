<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { PhCaretLeft, PhCaretRight } from '@phosphor-icons/vue'

import type { DiaryEntry } from '@/shared/api/diary'
import { toIsoDate } from '@/shared/utils/diaryFormat'

const props = defineProps<{
  entries: DiaryEntry[]
  selectedDate: string | null
}>()

const emit = defineEmits<{
  selectDate: [isoDate: string]
}>()

const viewMonth = ref(new Date())

const monthLabel = computed(() =>
  viewMonth.value.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long' }),
)

const datesWithEntries = computed(() => {
  const set = new Set<string>()
  for (const entry of props.entries) {
    if (entry.date) set.add(entry.date)
  }
  return set
})

const calendarCells = computed(() => {
  const year = viewMonth.value.getFullYear()
  const month = viewMonth.value.getMonth()
  const firstDay = new Date(year, month, 1)
  const startOffset = firstDay.getDay() === 0 ? 6 : firstDay.getDay() - 1
  const daysInMonth = new Date(year, month + 1, 0).getDate()

  const cells: Array<{ iso: string | null; day: number | null; hasEntry: boolean }> = []

  for (let i = 0; i < startOffset; i += 1) {
    cells.push({ iso: null, day: null, hasEntry: false })
  }

  for (let day = 1; day <= daysInMonth; day += 1) {
    const date = new Date(year, month, day)
    const iso = toIsoDate(date)
    cells.push({
      iso,
      day,
      hasEntry: datesWithEntries.value.has(iso),
    })
  }

  return cells
})

function prevMonth() {
  const next = new Date(viewMonth.value)
  next.setMonth(next.getMonth() - 1)
  viewMonth.value = next
}

function nextMonth() {
  const next = new Date(viewMonth.value)
  next.setMonth(next.getMonth() + 1)
  viewMonth.value = next
}

function onSelect(iso: string | null) {
  if (!iso) return
  emit('selectDate', iso)
}

watch(
  () => props.selectedDate,
  (iso) => {
    if (!iso) return
    const date = new Date(`${iso}T00:00:00`)
    if (!Number.isNaN(date.getTime())) {
      viewMonth.value = new Date(date.getFullYear(), date.getMonth(), 1)
    }
  },
  { immediate: true },
)
</script>

<template>
  <div class="calendar-view">
    <div class="calendar-view__nav">
      <button type="button" class="calendar-view__nav-btn" @click="prevMonth">
        <PhCaretLeft :size="14" />
      </button>
      <span class="calendar-view__month">{{ monthLabel }}</span>
      <button type="button" class="calendar-view__nav-btn" @click="nextMonth">
        <PhCaretRight :size="14" />
      </button>
    </div>

    <div class="calendar-view__weekdays">
      <span v-for="label in ['一', '二', '三', '四', '五', '六', '日']" :key="label">
        {{ label }}
      </span>
    </div>

    <div class="calendar-view__grid">
      <button
        v-for="(cell, index) in calendarCells"
        :key="`${cell.iso ?? 'empty'}-${index}`"
        type="button"
        class="calendar-view__cell"
        :class="{
          'is-empty': !cell.day,
          'has-entry': cell.hasEntry,
          'is-selected': cell.iso && cell.iso === selectedDate,
        }"
        :disabled="!cell.day"
        @click="onSelect(cell.iso)"
      >
        <span v-if="cell.day">{{ cell.day }}</span>
        <span v-if="cell.hasEntry" class="calendar-view__sticker" aria-hidden="true" />
      </button>
    </div>
  </div>
</template>

<style scoped>
.calendar-view {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.calendar-view__nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.calendar-view__nav-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  border-radius: 0.5rem;
  border: 1px solid var(--color-border);
  background: var(--color-surface-raised);
  color: var(--color-text-secondary);
}

.calendar-view__month {
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.calendar-view__weekdays {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 0.25rem;
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
  text-align: center;
}

.calendar-view__grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 0.25rem;
}

.calendar-view__cell {
  position: relative;
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 0.5rem;
  border: 1px solid transparent;
  background: var(--color-surface-raised);
  font-size: 0.8125rem;
  color: var(--color-text-primary);
  transition:
    border-color 0.2s ease,
    background 0.2s ease;
}

.calendar-view__cell.is-empty {
  visibility: hidden;
  pointer-events: none;
}

.calendar-view__cell.has-entry:not(.is-selected):hover {
  border-color: var(--color-border);
}

.calendar-view__cell.is-selected {
  border-color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 14%, var(--color-surface-raised));
}

.calendar-view__sticker {
  position: absolute;
  bottom: 0.25rem;
  width: 0.375rem;
  height: 0.375rem;
  border-radius: 50%;
  background: var(--color-accent);
}
</style>
