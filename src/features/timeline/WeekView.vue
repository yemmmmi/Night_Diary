<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { PhCaretLeft, PhCaretRight } from '@phosphor-icons/vue'

import DayDetailDrawer from '@/features/home/DayDetailDrawer.vue'
import EmotionChips from '@/features/card/EmotionChips.vue'
import WeekMoodChart from '@/features/timeline/WeekMoodChart.vue'
import WeeklyLetterCard from '@/features/timeline/WeeklyLetterCard.vue'
import { timelineCopy as copy } from '@/shared/copy/timeline'
import { cardCopy } from '@/shared/copy/card'
import { useTimelineStore } from '@/stores/timeline'
import { useCardStore } from '@/stores/card'
import type { DiaryEntry } from '@/shared/api/diary'
import type { MemoryCard } from '@/shared/api/card'
import {
  diaryStatus,
  diarySummary,
  formatWeekRangeLabel,
  groupEntriesForWeek,
  toIsoDate,
  weekdayLabel,
} from '@/shared/utils/diaryFormat'
import {
  sortKanbanItems,
  splitKanbanItems,
  type KanbanItem,
} from '@/shared/utils/kanbanSort'

const router = useRouter()
const timeline = useTimelineStore()
const cardStore = useCardStore()

type WeekColumn = {
  key: string
  label: string
  isToday: boolean
  dayNumber: number
  visibleItems: KanbanItem[]
  overflowCount: number
  allItems: KanbanItem[]
}

const dayDrawer = ref<{ title: string; items: KanbanItem[] } | null>(null)

const EMOTION_COLORS: Record<string, string> = {
  '开心': '#4CAF50',
  '平静': '#607D8B',
  '感激': '#D4A574',
  '期待': '#26A69A',
  '兴奋': '#FF9800',
  '焦虑': '#7E57C2',
  '疲惫': '#9E9E9E',
  '悲伤': '#5C6BC0',
  '迷茫': '#78909C',
  '愤怒': '#EF5350',
}

function cardEmotionColor(card: MemoryCard): string {
  return EMOTION_COLORS[card.emotion] ?? 'var(--color-accent)'
}

const weekLabel = computed(() =>
  formatWeekRangeLabel(timeline.weekStart, timeline.weekEnd),
)

const weekStats = computed(() => {
  const cards = cardStore.cards.filter((c) => {
    const d = c.created_at.slice(0, 10)
    return d >= timeline.weekStartIso && d <= timeline.weekEndIso
  })
  const done = timeline.tasks.filter((t) => t.status === 'done').length
  return {
    diary: timeline.entries.length,
    card: cards.length,
    taskDone: done,
    taskTotal: timeline.tasks.length,
  }
})

const weekColumns = computed(() => {
  const { dayColumns } = groupEntriesForWeek(
    timeline.entries,
    timeline.weekStart,
    timeline.weekEnd,
  )

  const cardByDiaryId = new Map<number, MemoryCard>()
  const standaloneCardsByDate = new Map<string, MemoryCard[]>()
  for (const card of cardStore.cards) {
    if (card.diary_id != null) {
      cardByDiaryId.set(card.diary_id, card)
    } else {
      const date = card.created_at.slice(0, 10)
      const arr = standaloneCardsByDate.get(date)
      if (arr) arr.push(card)
      else standaloneCardsByDate.set(date, [card])
    }
  }

  const days = Array.from({ length: 7 }, (_, index) => {
    const date = new Date(timeline.weekStart)
    date.setDate(date.getDate() + index)
    const iso = toIsoDate(date)
    const diaryEntries = dayColumns.get(iso) ?? []
    const standaloneCards = standaloneCardsByDate.get(iso) ?? []

    const items: KanbanItem[] = [
      ...diaryEntries.map((e): KanbanItem => ({
        kind: 'diary',
        entry: e,
        linkedCard: cardByDiaryId.get(e.id) ?? null,
      })),
      ...standaloneCards.map((c): KanbanItem => ({ kind: 'card', card: c })),
    ]
    const sorted = sortKanbanItems(items)
    const { visible, overflowCount } = splitKanbanItems(sorted)

    return {
      key: iso,
      label: weekdayLabel(date),
      isToday: iso === timeline.todayIso,
      dayNumber: date.getDate(),
      visibleItems: visible,
      overflowCount,
      allItems: sorted,
    }
  })

  return days as WeekColumn[]
})

function openEntry(entry: DiaryEntry) {
  timeline.selectEntry(entry.id)
}

function openCard(card: MemoryCard) {
  if (card.diary_id) {
    router.push(`/write/${card.diary_id}`)
    return
  }
  cardStore
    .expandCard(card.card_id)
    .then((result) => {
      void timeline.load()
      router.push(`/write/${result.diary_id}`)
    })
    .catch(() => {
      /* handled by store */
    })
}

function openDayDrawer(column: WeekColumn) {
  if (column.allItems.length === 0) return
  const title = column.isToday
    ? `${column.label} ${copy.todayTag} ${column.dayNumber}日`
    : copy.dayDrawerTitle(column.label, column.dayNumber)
  dayDrawer.value = { title, items: column.allItems }
}

function closeDayDrawer() {
  dayDrawer.value = null
}

function onDrawerOpenDiary(entry: DiaryEntry) {
  closeDayDrawer()
  openEntry(entry)
}

function onDrawerOpenCard(card: MemoryCard) {
  closeDayDrawer()
  openCard(card)
}

function createForDate(isoDate: string | null) {
  if (isoDate) {
    router.push({ path: '/write', query: { date: isoDate } })
    return
  }
  router.push('/write')
}
</script>

<template>
  <section class="week-view">
    <div class="week-view__nav">
      <button type="button" class="week-view__nav-btn" @click="timeline.shiftPeriod(-1)">
        <PhCaretLeft :size="14" />
        {{ copy.prevWeek }}
      </button>
      <span class="week-view__label">{{ weekLabel }}</span>
      <button type="button" class="week-view__nav-btn" @click="timeline.shiftPeriod(1)">
        {{ copy.nextWeek }}
        <PhCaretRight :size="14" />
      </button>
    </div>

    <div class="week-view__overview">
      <WeekMoodChart :points="timeline.moodTrend" />
      <p class="week-view__stats">
        {{ copy.weekOverview(weekStats.diary, weekStats.card, weekStats.taskDone, weekStats.taskTotal) }}
      </p>
    </div>

    <div class="week-view__kanban" :class="{ 'is-loading': timeline.loading }">
      <div
        v-for="column in weekColumns"
        :key="column.key"
        class="kanban-col"
        :class="{ 'kanban-col--today': column.isToday }"
      >
        <div class="kanban-col__head">
          <span class="kanban-col__label">
            {{ column.label }}
            <span v-if="column.isToday" class="kanban-col__today">{{ copy.todayTag }}</span>
          </span>
          <span class="kanban-col__day">{{ column.dayNumber }}</span>
        </div>

        <template
          v-for="item in column.visibleItems"
          :key="item.kind === 'diary' ? `d-${item.entry.id}` : `c-${item.card.card_id}`"
        >
          <button
            v-if="item.kind === 'diary'"
            type="button"
            class="kanban-card"
            :class="{ 'kanban-card--replied': diaryStatus(item.entry) === 'reply' }"
            @click="openEntry(item.entry)"
          >
            <span class="kanban-card__summary">{{
              diarySummary(item.entry.content, 28, item.linkedCard?.event_summary)
            }}</span>
            <div class="kanban-card__footer">
              <EmotionChips
                v-if="item.linkedCard"
                class="kanban-card__emotion"
                :emotions="item.linkedCard.emotions"
                :emotion="item.linkedCard.emotion"
                :size="12"
                compact
                :max-count="1"
              />
            </div>
          </button>

          <button
            v-else
            type="button"
            class="kanban-card kanban-card--card"
            :style="{ borderLeftColor: cardEmotionColor(item.card) }"
            @click="openCard(item.card)"
          >
            <span v-if="item.card.event_summary" class="kanban-card__summary">
              {{ diarySummary(item.card.event_summary, 32) }}
            </span>
            <span v-else class="kanban-card__summary kanban-card__summary--muted">
              {{ cardCopy.recordedMoodOnly }}
            </span>
            <div class="kanban-card__footer">
              <EmotionChips
                class="kanban-card__emotion"
                :emotions="item.card.emotions"
                :emotion="item.card.emotion"
                :size="12"
                compact
                :max-count="1"
              />
            </div>
          </button>
        </template>

        <button
          v-if="column.overflowCount > 0"
          type="button"
          class="kanban-more"
          @click="openDayDrawer(column)"
        >
          {{ copy.moreRecords(column.overflowCount) }}
        </button>

        <button type="button" class="kanban-add" @click="createForDate(column.key)">+</button>
      </div>
    </div>

    <WeeklyLetterCard :week-start-iso="timeline.weekStartIso" />

    <Teleport to="body">
      <DayDetailDrawer
        v-if="dayDrawer"
        :title="dayDrawer.title"
        :items="dayDrawer.items"
        @close="closeDayDrawer"
        @open-diary="onDrawerOpenDiary"
        @open-card="onDrawerOpenCard"
      />
    </Teleport>
  </section>
</template>

<style scoped>
.week-view {
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
}
.week-view__nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}
.week-view__nav-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 0.8125rem;
  cursor: pointer;
  padding: 0.25rem 0.375rem;
}
.week-view__nav-btn:hover {
  color: var(--color-text-primary);
}
.week-view__label {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-text-primary);
}
.week-view__overview {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.5rem 0.75rem;
}
.week-view__stats {
  margin: 0;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  white-space: nowrap;
}
.week-view__kanban.is-loading {
  opacity: 0.65;
  pointer-events: none;
}
.week-view__kanban {
  display: flex;
  gap: 0.5rem;
  overflow-x: auto;
  padding-bottom: 0.5rem;
}
.kanban-col {
  min-width: 7.5rem;
  flex: 1;
  flex-shrink: 0;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: 0.875rem;
  padding: 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
.kanban-col__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-text-secondary);
  padding: 0 0.125rem;
}

.kanban-col--today {
  border-color: color-mix(in srgb, var(--color-accent) 55%, var(--color-border));
  box-shadow:
    0 0 0 1px color-mix(in srgb, var(--color-accent) 20%, transparent),
    0 2px 8px color-mix(in srgb, var(--color-accent) 10%, transparent);
  position: relative;
  overflow: hidden;
}

.kanban-col--today::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, var(--color-accent), color-mix(in srgb, var(--color-accent) 60%, #fff));
  border-bottom-left-radius: 0.875rem;
  border-bottom-right-radius: 0.875rem;
}

.kanban-col--today .kanban-col__day {
  font-weight: 700;
  color: var(--color-accent);
}

.kanban-col__label {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
}

.kanban-col__today {
  font-size: 0.625rem;
  font-weight: 600;
  color: #fff;
  background: var(--color-accent);
  padding: 0.125rem 0.375rem;
  border-radius: 999px;
  line-height: 1;
}

.kanban-col__day {
  font-size: 0.875rem;
  color: var(--color-text-primary);
}
.kanban-card {
  width: 100%;
  text-align: left;
  border: 1px solid var(--color-border);
  border-radius: 0.625rem;
  background: var(--color-bg-elevated-2);
  padding: 0.4375rem 0.5rem;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  transition: transform var(--motion-duration) var(--motion-ease);
}
.kanban-card:hover {
  transform: translateY(-1px);
}

/* Card variant: left emotion-colored border */
.kanban-card--card {
  border-left-width: 3px;
  border-left-style: solid;
}

/* Diary card with AI reply: subtle green left edge */
.kanban-card--replied {
  border-left-width: 3px;
  border-left-style: solid;
  border-left-color: color-mix(in srgb, var(--color-success) 60%, var(--color-border));
}

.kanban-card__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.25rem;
  min-height: 1.125rem;
}

.kanban-card__emotion {
  flex-shrink: 0;
}

.kanban-card__summary {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
  font-size: 0.75rem;
  line-height: 1.4;
  color: var(--color-text-primary);
}

.kanban-card__summary--muted {
  color: var(--color-text-secondary);
  font-style: italic;
}

.kanban-more {
  width: 100%;
  border: none;
  border-radius: 0.375rem;
  background: color-mix(in srgb, var(--color-accent) 8%, transparent);
  color: var(--color-accent);
  font-size: 0.6875rem;
  font-weight: 600;
  padding: 0.3125rem 0.375rem;
  cursor: pointer;
  text-align: center;
}

.kanban-more:hover {
  background: color-mix(in srgb, var(--color-accent) 14%, transparent);
}

.kanban-add {
  width: 100%;
  border: 1px dashed var(--color-border);
  border-radius: 0.375rem;
  background: transparent;
  color: var(--color-text-secondary);
  padding: 0.25rem;
  cursor: pointer;
  margin-top: auto;
}
.kanban-add:hover {
  color: var(--color-text-primary);
  border-color: var(--color-accent-muted);
}
</style>
