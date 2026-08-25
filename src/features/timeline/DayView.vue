<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { PhCaretLeft, PhCaretRight } from '@phosphor-icons/vue'

import EmotionChips from '@/features/card/EmotionChips.vue'
import GameButton from '@/shared/components/GameButton.vue'
import GlassPanel from '@/shared/components/GlassPanel.vue'
import TaskFoldRow from '@/features/timeline/TaskFoldRow.vue'
import { timelineCopy as copy } from '@/shared/copy/timeline'
import { cardCopy } from '@/shared/copy/card'
import { useTimelineStore } from '@/stores/timeline'
import { useCardStore } from '@/stores/card'
import { usePlanStore } from '@/stores/plan'
import {
  diaryStatus,
  diarySummary,
  parseLocalDate,
  weekdayLabel,
} from '@/shared/utils/diaryFormat'
import type { MemoryCard } from '@/shared/api/card'

const router = useRouter()
const timeline = useTimelineStore()
const cardStore = useCardStore()
const planStore = usePlanStore()

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

const dayLabel = computed(() => {
  const d = parseLocalDate(timeline.date)
  return `${d.getMonth() + 1}月${d.getDate()}日 ${weekdayLabel(d)}`
})

const dayCards = computed(() =>
  cardStore.cards.filter(
    (c) => c.diary_id == null && c.created_at.slice(0, 10) === timeline.date,
  ),
)

const isEmptyDay = computed(
  () => !timeline.loading && timeline.entries.length === 0 && dayCards.value.length === 0,
)

function cardEmotionColor(card: MemoryCard): string {
  return EMOTION_COLORS[card.emotion] ?? 'var(--color-accent)'
}

function openEntry(entryId: number) {
  router.push(`/write/${entryId}`)
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

function createForDate() {
  router.push({ path: '/write', query: { date: timeline.date } })
}

onMounted(() => {
  if (timeline.isToday) void planStore.loadTodayTasks()
})
</script>

<template>
  <section class="day-view">
    <div class="day-view__nav">
      <button type="button" class="day-view__nav-btn" @click="timeline.shiftPeriod(-1)">
        <PhCaretLeft :size="14" />
        {{ copy.prevDay }}
      </button>
      <span class="day-view__label" :class="{ 'is-today': timeline.isToday }">
        {{ dayLabel }}
        <span v-if="timeline.isToday" class="day-view__today">{{ copy.todayTag }}</span>
      </span>
      <button type="button" class="day-view__nav-btn" @click="timeline.shiftPeriod(1)">
        {{ copy.nextDay }}
        <PhCaretRight :size="14" />
      </button>
      <button
        v-if="!timeline.isToday"
        type="button"
        class="day-view__nav-btn"
        @click="timeline.goToday()"
      >
        {{ copy.backToToday }}
      </button>
    </div>

    <section v-if="isEmptyDay" class="day-view__empty">
      <p class="day-view__empty-title">{{ copy.emptyTitle }}</p>
      <p class="day-view__empty-hint">{{ copy.emptyHint }}</p>
      <GameButton variant="primary" @click="createForDate">{{ copy.emptyCta }}</GameButton>
    </section>

    <template v-else>
      <GlassPanel
        v-for="entry in timeline.entries"
        :key="entry.id"
        class="day-view__diary"
        :class="{ 'is-replied': diaryStatus(entry) === 'reply' }"
      >
        <div class="day-view__diary-head">
          <span class="day-view__diary-date">{{ timeline.date }}</span>
          <span v-if="entry.weather" class="day-view__diary-weather">{{ entry.weather }}</span>
        </div>
        <button type="button" class="day-view__diary-body" @click="timeline.selectEntry(entry.id)">
          <span class="day-view__diary-preview font-diary">
            {{ diarySummary(entry.content, 120) }}
          </span>
        </button>
        <div class="day-view__diary-actions">
          <button type="button" class="day-view__diary-continue" @click="openEntry(entry.id)">
            {{ copy.writeDiary }}
          </button>
        </div>
      </GlassPanel>

      <TaskFoldRow v-if="timeline.isToday" class="day-view__tasks" />

      <GlassPanel
        v-for="card in dayCards"
        :key="card.card_id"
        class="day-view__card"
        :style="{ borderLeftColor: cardEmotionColor(card) }"
      >
        <button type="button" class="day-view__card-body" @click="openCard(card)">
          <span class="day-view__card-summary font-diary">
            {{ diarySummary(card.event_summary, 60, cardCopy.recordedMoodOnly) }}
          </span>
          <EmotionChips
            class="day-view__card-emotion"
            :emotions="card.emotions"
            :emotion="card.emotion"
            :size="12"
            compact
            :max-count="1"
          />
        </button>
      </GlassPanel>
    </template>
  </section>
</template>

<style scoped>
.day-view {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.day-view__nav {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.day-view__nav-btn {
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
.day-view__nav-btn:hover {
  color: var(--color-text-primary);
}
.day-view__label {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-text-primary);
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
}
.day-view__today {
  font-size: 0.625rem;
  font-weight: 600;
  color: #fff;
  background: var(--color-accent);
  padding: 0.125rem 0.375rem;
  border-radius: 999px;
  line-height: 1;
}
.day-view__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  padding: 3rem 1.5rem;
  text-align: center;
  border: 1px dashed var(--color-border);
  border-radius: 0.875rem;
}
.day-view__empty-title {
  font-size: 1rem;
  font-weight: 600;
  color: var(--color-text-primary);
}
.day-view__empty-hint {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  margin-bottom: 0.75rem;
}
.day-view__diary.is-replied {
  border-left: 3px solid color-mix(in srgb, var(--color-success) 60%, var(--color-border));
}
.day-view__diary-head {
  display: flex;
  align-items: baseline;
  gap: 0.625rem;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}
.day-view__diary-body {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.375rem;
  width: 100%;
  border: none;
  background: transparent;
  cursor: pointer;
  text-align: left;
  padding: 0;
}
.day-view__diary-preview {
  font-size: 0.875rem;
  line-height: 1.6;
  color: var(--color-text-primary);
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 4;
  overflow: hidden;
}
.day-view__diary-actions {
  display: flex;
  justify-content: flex-end;
}
.day-view__diary-continue {
  border: none;
  background: transparent;
  color: var(--color-accent, #d4a574);
  font-size: 0.8125rem;
  cursor: pointer;
  padding: 0.25rem 0;
}
.day-view__diary-continue:hover {
  text-decoration: underline;
}
.day-view__card {
  border-left: 3px solid var(--color-accent);
}
.day-view__card-body {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  width: 100%;
  border: none;
  background: transparent;
  cursor: pointer;
  text-align: left;
  padding: 0;
}
.day-view__card-summary {
  font-size: 0.8125rem;
  color: var(--color-text-primary);
}
</style>
