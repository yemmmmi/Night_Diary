<script setup lang="ts">
import { computed } from 'vue'
import { PhCaretLeft, PhCaretRight } from '@phosphor-icons/vue'

import { timelineCopy as copy } from '@/shared/copy/timeline'
import { useTimelineStore } from '@/stores/timeline'
import { parseLocalDate, toIsoDate } from '@/shared/utils/diaryFormat'

const timeline = useTimelineStore()

const monthLabel = computed(() =>
  parseLocalDate(timeline.date).toLocaleDateString('zh-CN', { year: 'numeric', month: 'long' }),
)

const datesWithEntries = computed(
  () => new Set(timeline.entries.map((e) => e.date).filter((d): d is string => Boolean(d))),
)

const calendarCells = computed(() => {
  const anchor = parseLocalDate(timeline.date)
  const year = anchor.getFullYear()
  const month = anchor.getMonth()
  const firstDay = new Date(year, month, 1)
  const startOffset = firstDay.getDay() === 0 ? 6 : firstDay.getDay() - 1
  const daysInMonth = new Date(year, month + 1, 0).getDate()

  const cells: Array<{ iso: string | null; day: number | null; hasEntry: boolean }> = []
  for (let i = 0; i < startOffset; i += 1) {
    cells.push({ iso: null, day: null, hasEntry: false })
  }
  for (let day = 1; day <= daysInMonth; day += 1) {
    const iso = toIsoDate(new Date(year, month, day))
    cells.push({ iso, day, hasEntry: datesWithEntries.value.has(iso) })
  }
  return cells
})

async function openDay(iso: string | null) {
  if (!iso) return
  await timeline.setDate(iso)
  await timeline.setView('day')
}
</script>

<template>
  <section class="month-view">
    <div class="month-view__nav">
      <button type="button" class="month-view__nav-btn" @click="timeline.shiftPeriod(-1)">
        <PhCaretLeft :size="14" />
      </button>
      <span class="month-view__label">{{ monthLabel }}</span>
      <button type="button" class="month-view__nav-btn" @click="timeline.shiftPeriod(1)">
        <PhCaretRight :size="14" />
      </button>
      <button
        v-if="!timeline.isToday"
        type="button"
        class="month-view__nav-btn month-view__back"
        @click="timeline.goToday()"
      >
        {{ copy.backToToday }}
      </button>
    </div>

    <div class="month-view__weekdays">
      <span v-for="label in ['一', '二', '三', '四', '五', '六', '日']" :key="label">
        {{ label }}
      </span>
    </div>

    <div class="month-view__grid">
      <button
        v-for="(cell, index) in calendarCells"
        :key="`${cell.iso ?? 'empty'}-${index}`"
        type="button"
        class="month-view__cell"
        :class="{
          'is-empty': !cell.day,
          'has-entry': cell.hasEntry,
          'is-today': cell.iso === timeline.todayIso,
        }"
        :data-iso="cell.iso"
        :disabled="!cell.day"
        @click="openDay(cell.iso)"
      >
        <span v-if="cell.day">{{ cell.day }}</span>
        <span v-if="cell.hasEntry" class="month-view__dot" aria-hidden="true" />
      </button>
    </div>
  </section>
</template>

<style scoped>
.month-view {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.month-view__nav {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.month-view__nav-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.25rem;
  width: 2rem;
  height: 2rem;
  border-radius: 0.5rem;
  border: 1px solid var(--color-border);
  background: var(--color-surface-raised);
  color: var(--color-text-secondary);
  cursor: pointer;
}
.month-view__back {
  width: auto;
  padding: 0 0.5rem;
  font-size: 0.8125rem;
}
.month-view__label {
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text-primary);
}
.month-view__weekdays {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 0.25rem;
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
  text-align: center;
}
.month-view__grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 0.25rem;
}
.month-view__cell {
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
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    background 0.2s ease;
}
.month-view__cell.is-empty {
  visibility: hidden;
  pointer-events: none;
}
.month-view__cell.has-entry:hover {
  border-color: var(--color-border);
}
.month-view__cell.is-today {
  border-color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 14%, var(--color-surface-raised));
  font-weight: 600;
}
.month-view__dot {
  position: absolute;
  bottom: 0.25rem;
  width: 0.375rem;
  height: 0.375rem;
  border-radius: 50%;
  background: var(--color-accent);
}
</style>
