<script setup lang="ts">
import { computed } from 'vue'
import { PhBooks, PhEnvelopeSimple } from '@phosphor-icons/vue'

import type { MemoryCard } from '@/shared/api/card'
import type { DiaryEntry } from '@/shared/api/diary'
import { diaryEntrySummary, diaryStatus, diaryStatusLabel } from '@/shared/utils/diaryFormat'

const props = withDefaults(
  defineProps<{
    entries: DiaryEntry[]
    selectedId: number | null
    cards?: MemoryCard[]
  }>(),
  {
    cards: () => [],
  },
)

const emit = defineEmits<{
  select: [entry: DiaryEntry]
}>()

interface MonthShelf {
  key: string
  label: string
  entries: DiaryEntry[]
}

const shelves = computed(() => {
  const map = new Map<string, DiaryEntry[]>()

  const sorted = [...props.entries].sort((a, b) => {
    const dateA = a.date ?? a.created_at.slice(0, 10)
    const dateB = b.date ?? b.created_at.slice(0, 10)
    return dateB.localeCompare(dateA)
  })

  for (const entry of sorted) {
    const raw = entry.date ?? entry.created_at.slice(0, 10)
    const [year, month] = raw.split('-')
    const key = `${year}-${month}`
    const bucket = map.get(key) ?? []
    bucket.push(entry)
    map.set(key, bucket)
  }

  const result: MonthShelf[] = []
  for (const [key, items] of map.entries()) {
    const [year, month] = key.split('-')
    const label = `${year}年${Number(month)}月`
    result.push({ key, label, entries: items })
  }

  return result.sort((a, b) => b.key.localeCompare(a.key))
})

const entrySummaries = computed(() => {
  const summaries = new Map<number, string>()
  for (const entry of props.entries) {
    summaries.set(entry.id, diaryEntrySummary(entry, props.cards, 28))
  }
  return summaries
})

function formatEntryDate(entry: DiaryEntry): string {
  const raw = entry.date ?? entry.created_at.slice(0, 10)
  const date = new Date(`${raw}T00:00:00`)
  return date.toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'short' })
}
</script>

<template>
  <div class="timeline-view">
    <section v-for="shelf in shelves" :key="shelf.key" class="timeline-shelf">
      <div class="timeline-shelf__head">
        <PhBooks :size="18" weight="duotone" class="timeline-shelf__icon" />
        <h3 class="timeline-shelf__title">{{ shelf.label }}</h3>
        <span class="timeline-shelf__count">{{ shelf.entries.length }} 篇</span>
      </div>

      <button
        v-for="entry in shelf.entries"
        :key="entry.id"
        type="button"
        class="timeline-entry"
        :class="{ 'is-selected': entry.id === selectedId }"
        @click="emit('select', entry)"
      >
        <div class="timeline-entry__meta">
          <span>{{ formatEntryDate(entry) }}</span>
          <span
              v-if="diaryStatusLabel(diaryStatus(entry))"
              class="timeline-entry__chip"
            >{{ diaryStatusLabel(diaryStatus(entry)) }}</span>
        </div>
        <p class="timeline-entry__summary font-diary">{{ entrySummaries.get(entry.id) }}</p>
        <PhEnvelopeSimple
          v-if="entry.ai_ans?.trim()"
          :size="14"
          class="timeline-entry__reply-icon"
          aria-label="已有回信"
        />
      </button>
    </section>

    <p v-if="shelves.length === 0" class="timeline-view__empty">还没有日记，去首页写一篇吧</p>
  </div>
</template>

<style scoped>
.timeline-view {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.timeline-shelf__head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.625rem;
}

.timeline-shelf__icon {
  color: var(--color-accent);
}

.timeline-shelf__title {
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.timeline-shelf__count {
  margin-left: auto;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

.timeline-entry {
  display: block;
  width: 100%;
  text-align: left;
  padding: 0.75rem 0.875rem;
  margin-bottom: 0.375rem;
  border-radius: 0.625rem;
  border: 1px solid var(--color-border);
  background: var(--color-surface-raised);
  transition:
    border-color 0.2s ease,
    background 0.2s ease;
}

.timeline-entry:hover,
.timeline-entry.is-selected {
  border-color: color-mix(in srgb, var(--color-accent) 45%, var(--color-border));
  background: color-mix(in srgb, var(--color-accent) 8%, var(--color-surface-raised));
}

.timeline-entry__meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  margin-bottom: 0.375rem;
}

.timeline-entry__chip {
  padding: 0.125rem 0.375rem;
  border-radius: 999px;
  font-size: 0.6875rem;
  background: var(--color-surface-sunken);
}

.timeline-entry__summary {
  font-size: 0.875rem;
  color: var(--color-text-primary);
  line-height: 1.5;
}

.timeline-entry__reply-icon {
  margin-top: 0.375rem;
  color: var(--color-accent);
}

.timeline-view__empty {
  text-align: center;
  font-size: 0.875rem;
  color: var(--color-text-secondary);
  padding: 2rem 0;
}
</style>
