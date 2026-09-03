<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { useRouter } from 'vue-router'
import { PhCaretLeft, PhCaretRight } from '@phosphor-icons/vue'

import EmotionChips from '@/features/card/EmotionChips.vue'
import GameButton from '@/shared/components/GameButton.vue'
import { timelineCopy as copy } from '@/shared/copy/timeline'
import { cardCopy } from '@/shared/copy/card'
import { useTimelineStore } from '@/stores/timeline'
import { useCardStore } from '@/stores/card'
import {
  diaryStatus,
  diarySummary,
} from '@/shared/utils/diaryFormat'
import { chineseDateLabel, todaySubtitle } from '@/shared/utils/todayFormat'
import { serverDateIso } from '@/shared/utils/timeFormat'
import type { MemoryCard } from '@/shared/api/card'

const router = useRouter()
const timeline = useTimelineStore()
const cardStore = useCardStore()

const bigDate = computed(() => chineseDateLabel(timeline.date))
const subtitle = computed(() => todaySubtitle(timeline.date))

const dayCards = computed(() =>
  cardStore.cards.filter(
    (c) => c.diary_id == null && serverDateIso(c.created_at) === timeline.date,
  ),
)

const isEmptyDay = computed(
  () => !timeline.loading && timeline.entries.length === 0 && dayCards.value.length === 0,
)

/** 翻页方向：prev 向右滑入、next 向左滑入（motion.css page-turn）。 */
const turnDir = ref<'prev' | 'next' | null>(null)

const turnClass = computed(() =>
  turnDir.value === 'prev' ? 'page-turn-right' : turnDir.value === 'next' ? 'page-turn-left' : '',
)

async function shiftWithTurn(delta: number) {
  const dir: 'prev' | 'next' = delta < 0 ? 'prev' : 'next'
  turnDir.value = null
  await timeline.shiftPeriod(delta)
  // 先清类再挂新类，保证连续点击时动画能重新触发。
  await nextTick()
  turnDir.value = dir
}

/** 翻页动画播完后清掉方向类，DOM 回到无动效基态。 */
function onTurnEnd(event: AnimationEvent) {
  if (event.animationName.startsWith('page-turn')) turnDir.value = null
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
</script>

<template>
  <section class="day-view">
    <header class="day-view__head">
      <button
        type="button"
        class="day-view__nav"
        data-testid="day-prev"
        aria-label="前一天"
        @click="shiftWithTurn(-1)"
      >
        <PhCaretLeft :size="16" />
      </button>
      <div class="day-view__head-center">
        <h1 class="day-view__big-date" data-testid="day-big-date">{{ bigDate }}</h1>
        <p class="day-view__sub">
          {{ subtitle }}
          <span v-if="timeline.isToday" class="day-view__today-tag">{{ copy.todayTag }}</span>
        </p>
      </div>
      <button
        type="button"
        class="day-view__nav"
        data-testid="day-next"
        aria-label="后一天"
        :disabled="timeline.isToday"
        @click="shiftWithTurn(1)"
      >
        <PhCaretRight :size="16" />
      </button>
      <button
        v-if="!timeline.isToday"
        type="button"
        class="day-view__back-today"
        data-testid="day-back-today"
        @click="timeline.goToday()"
      >
        {{ copy.backToToday }}
      </button>
    </header>

    <div class="day-view__body" :class="turnClass" @animationend="onTurnEnd">
      <section v-if="isEmptyDay" class="day-view__empty">
        <div class="day-view__empty-icon" aria-hidden="true">
          <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
            <rect x="10" y="6" width="28" height="36" rx="4" stroke="currentColor" stroke-width="2" opacity="0.5" />
            <path d="M16 18h16M16 24h12" stroke="currentColor" stroke-width="2" stroke-linecap="round" opacity="0.3" />
            <path d="M24 32v-6m-3 3h6" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
          </svg>
        </div>
        <p class="day-view__empty-title">{{ copy.emptyTitle }}</p>
        <p class="day-view__empty-hint">{{ copy.emptyHint }}</p>
        <GameButton variant="primary" @click="createForDate">{{ copy.emptyCta }}</GameButton>
      </section>

      <template v-else>
        <div
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
        </div>

        <div
          v-for="card in dayCards"
          :key="card.card_id"
          class="day-view__card"
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
        </div>
      </template>
    </div>
  </section>
</template>

<style scoped>
.day-view {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
/* 内容体：翻页方向滑入动画挂在它上面，导航按钮保持原位 */
.day-view__body {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.day-view__head {
  display: grid;
  grid-template-columns: auto 1fr auto auto;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1.5rem;
}
.day-view__head-center {
  text-align: center;
}
.day-view__big-date {
  font-family: var(--font-display);
  font-size: 2.25rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  line-height: 1.15;
  margin: 0;
  color: var(--color-text-primary);
}
.day-view__sub {
  margin: 0.375rem 0 0;
  font-size: 0.8125rem;
  color: var(--color-text-faint);
  letter-spacing: 0.08em;
}
.day-view__today-tag {
  font-size: 0.625rem;
  font-weight: 600;
  color: var(--color-accent);
  border: 1px solid var(--color-accent);
  padding: 0.125rem 0.375rem;
  border-radius: var(--radius-seal);
  line-height: 1;
  margin-left: 0.375rem;
  vertical-align: 0.0625rem;
}
.day-view__nav {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  border: none;
  border-radius: var(--radius-button);
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: color var(--dur-fast) var(--ease-out-quart),
    background var(--dur-fast) var(--ease-out-quart);
}
.day-view__nav:hover:not(:disabled) {
  color: var(--color-text-primary);
  background: var(--color-bg-elevated-2);
}
.day-view__nav:disabled {
  opacity: 0.35;
  cursor: default;
}
.day-view__back-today {
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 0.8125rem;
  cursor: pointer;
  padding: 0.25rem 0.375rem;
}
.day-view__back-today:hover {
  color: var(--color-text-primary);
}
.day-view__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.375rem;
  padding: 3.5rem 1.5rem 3rem;
  text-align: center;
}
.day-view__empty-icon {
  color: var(--color-text-faint);
  opacity: 0.35;
  margin-bottom: 0.375rem;
}
.day-view__empty-title {
  font-family: var(--font-display);
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--color-text-primary);
}
.day-view__empty-hint {
  font-size: 0.8125rem;
  color: var(--color-text-faint);
  margin-bottom: 1rem;
}
.day-view__diary,
.day-view__card {
  padding: 0.875rem 0;
  border-bottom: 1px solid var(--color-line);
}
.day-view__diary:last-child,
.day-view__card:last-child {
  border-bottom: none;
}
.day-view__diary.is-replied {
  border-left: none;
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
  color: var(--color-accent);
  font-size: 0.8125rem;
  cursor: pointer;
  padding: 0.25rem 0;
}
.day-view__diary-continue:hover {
  text-decoration: underline;
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
