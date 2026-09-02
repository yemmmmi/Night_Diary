<script setup lang="ts">
import { onActivated, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PhNotePencil } from '@phosphor-icons/vue'

defineOptions({ name: 'TimelineScene' })

import DayView from '@/features/timeline/DayView.vue'
import WeekView from '@/features/timeline/WeekView.vue'
import MonthView from '@/features/timeline/MonthView.vue'
import TodayRail from '@/features/timeline/TodayRail.vue'
import DetailPanel from '@/features/timeline/DetailPanel.vue'
import MemoryCardInput from '@/features/card/MemoryCardInput.vue'
import EmotionChips from '@/features/card/EmotionChips.vue'
import GameButton from '@/shared/components/GameButton.vue'
import { timelineCopy as copy } from '@/shared/copy/timeline'
import { cardCopy } from '@/shared/copy/card'
import { useTimelineStore } from '@/stores/timeline'
import { useCardStore } from '@/stores/card'
import { usePlanStore } from '@/stores/plan'
import { buildTimelineQuery, parseTimelineQuery } from '@/shared/utils/timelineQuery'
import type { TimelineView } from '@/shared/utils/timelineQuery'
import { toIsoDate } from '@/shared/utils/diaryFormat'

const viewLabels: Record<TimelineView, string> = {
  day: copy.viewDay,
  week: copy.viewWeek,
  month: copy.viewMonth,
}

const route = useRoute()
const router = useRouter()
const timeline = useTimelineStore()
const cardStore = useCardStore()
const planStore = usePlanStore()

function loadRailData() {
  void planStore.loadTodayTasks()
  void planStore.loadPlans()
}

function syncFromRoute(force = false) {
  const { view, date } = parseTimelineQuery(route.query, toIsoDate(new Date()))
  if (!force && timeline.view === view && timeline.date === date) return
  timeline.view = view
  timeline.date = date
  void timeline.load()
}

watch(
  () => [timeline.view, timeline.date] as const,
  ([view, date]) => {
    if (route.query.view !== view || route.query.date !== date) {
      void router.replace({ query: buildTimelineQuery(view, date) })
    }
  },
)

watch(
  () => route.query,
  () => syncFromRoute(),
)

function writeForDate() {
  router.push({ path: '/write', query: { date: timeline.date } })
}

onMounted(() => {
  syncFromRoute(true)
  void cardStore.loadCards()
  loadRailData()
})

onActivated(() => {
  syncFromRoute(true)
  void cardStore.loadCards()
  loadRailData()
})
</script>

<template>
  <main class="timeline-scene">
    <header class="timeline-scene__header">
      <div class="timeline-scene__switcher" role="tablist">
        <button
          v-for="v in (['day', 'week', 'month'] as const)"
          :key="v"
          type="button"
          role="tab"
          class="timeline-scene__switch"
          :class="{ 'is-active': timeline.view === v }"
          :aria-selected="timeline.view === v"
          @click="timeline.setView(v)"
        >
          {{ viewLabels[v] }}
        </button>
      </div>
      <div class="timeline-scene__actions">
        <GameButton variant="ghost" @click="cardStore.openDrawer()">
          <PhNotePencil :size="16" />
          {{ cardCopy.newCard }}
        </GameButton>
        <GameButton @click="writeForDate">
          {{ copy.writeDiary }}
        </GameButton>
      </div>
    </header>

    <div v-if="timeline.error" class="timeline-scene__error">
      <span>{{ timeline.error }}</span>
      <GameButton variant="ghost" @click="timeline.load()">{{ copy.retry }}</GameButton>
    </div>

    <div class="timeline-scene__layout" :class="{ 'has-detail': timeline.selectedEntry }">
      <div class="timeline-scene__main" :class="{ 'is-day': timeline.view === 'day' }">
        <DayView v-if="timeline.view === 'day'" />
        <WeekView v-else-if="timeline.view === 'week'" />
        <MonthView v-else />
        <TodayRail v-if="timeline.view === 'day'" class="timeline-scene__rail" />
      </div>
      <aside v-if="timeline.selectedEntry" class="timeline-scene__detail">
        <DetailPanel />
      </aside>
    </div>

    <Teleport to="body">
      <Transition name="card-drawer">
        <div
          v-if="cardStore.showCardDrawer"
          class="card-drawer-backdrop"
          @click.self="cardStore.closeDrawer()"
        >
          <div class="card-drawer-panel">
            <div class="card-drawer-header">
              <h2 class="card-drawer-title">{{ cardCopy.newCard }}</h2>
              <button type="button" class="card-drawer-close" @click="cardStore.closeDrawer()">
                &times;
              </button>
            </div>
            <div class="card-drawer-body">
              <MemoryCardInput
                mode="standard"
                :auto-close="true"
                @saved="cardStore.loadCards()"
                @close="cardStore.closeDrawer()"
              />
            </div>
            <div v-if="cardStore.cards.length > 0" class="card-drawer-recent">
              <p class="card-drawer-recent-title">{{ cardCopy.recentCards }}</p>
              <div class="card-drawer-recent-list">
                <div
                  v-for="card in cardStore.cards.slice(0, 5)"
                  :key="card.card_id"
                  class="recent-card-item"
                >
                  <EmotionChips
                    class="recent-card-emotion"
                    :emotions="card.emotions"
                    :emotion="card.emotion"
                    :size="13"
                  />
                  <span v-if="card.event_summary" class="recent-card-summary">
                    {{ card.event_summary.slice(0, 40) }}{{ card.event_summary.length > 40 ? '…' : '' }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </main>
</template>

<style scoped>
.timeline-scene {
  min-height: calc(100vh - 2.5rem);
  padding: 1.25rem 1rem 1.5rem;
  max-width: 90rem;
  margin: 0 auto;
}
.timeline-scene__header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
}
.timeline-scene__switcher {
  display: inline-flex;
  gap: 0;
  border-bottom: 1px solid var(--color-line);
}
.timeline-scene__switch {
  position: relative;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 0.8125rem;
  font-weight: 500;
  padding: 0.5rem 0.875rem;
  cursor: pointer;
  transition:
    color var(--motion-duration) var(--motion-ease);
}
.timeline-scene__switch::after {
  content: '';
  position: absolute;
  bottom: -1px;
  left: 0;
  right: 0;
  height: 2px;
  background: var(--color-accent);
  transform: scaleX(0);
  transition: transform var(--dur-fast) var(--ease-out-quart);
}
.timeline-scene__switch:hover {
  color: var(--color-text-primary);
}
.timeline-scene__switch.is-active {
  color: var(--color-text-primary);
  font-weight: 600;
}
.timeline-scene__switch.is-active::after {
  transform: scaleX(1);
}
.timeline-scene__actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.timeline-scene__error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
  padding: 0.625rem 0.875rem;
  border-radius: 0.75rem;
  border: 1px solid color-mix(in srgb, var(--color-danger) 35%, var(--color-border));
  background: color-mix(in srgb, var(--color-danger) 8%, var(--color-bg-elevated));
  font-size: 0.8125rem;
  color: var(--color-danger);
}
.timeline-scene__layout {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1rem;
  align-items: start;
}
.timeline-scene__main {
  min-width: 0;
}
.timeline-scene__main.is-day {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 272px;
  gap: 0;
}
.timeline-scene__rail {
  min-width: 0;
}
.timeline-scene__detail {
  min-width: 0;
}
@media (max-width: 63.99rem) {
  .timeline-scene__main.is-day {
    grid-template-columns: 1fr;
  }
  .timeline-scene__rail {
    border-left: none;
    padding-left: 0;
    border-top: 1px solid var(--color-line);
    padding-top: 1.25rem;
    margin-top: 1.25rem;
  }
}
@media (min-width: 64rem) {
  .timeline-scene__layout.has-detail {
    grid-template-columns: 1fr min(20rem, 34%);
  }
  .timeline-scene__detail {
    position: sticky;
    top: 1rem;
    max-height: calc(100vh - 4rem);
    overflow-y: auto;
  }
}
@media (max-width: 63.99rem) {
  .timeline-scene__detail {
    position: fixed;
    inset: 0;
    z-index: 60;
    overflow-y: auto;
    padding: 4.5rem 1rem 1.5rem;
    background: color-mix(in srgb, var(--color-bg) 92%, transparent);
    backdrop-filter: blur(8px);
  }
}
</style>

<style>
/* Card drawer（从 HomeScene 迁移的全局样式，Teleport 到 body 需要） */
.card-drawer-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(0, 0, 0, 0.35);
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding: 3rem 1rem 1rem;
  overflow-y: auto;
}
.card-drawer-panel {
  width: 100%;
  max-width: 28rem;
  background: var(--color-bg-elevated);
  border-radius: var(--radius-outer, 1.5rem);
  border: 1px solid var(--color-border);
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.15);
  overflow: hidden;
}
.card-drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--color-border);
}
.card-drawer-title {
  font-family: var(--font-ui);
  font-size: 1rem;
  font-weight: 700;
  color: var(--color-text-primary);
}
.card-drawer-close {
  width: 1.75rem;
  height: 1.75rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  font-size: 1.25rem;
  color: var(--color-text-secondary);
  cursor: pointer;
  border-radius: 50%;
}
.card-drawer-close:hover {
  background: var(--color-bg-elevated-2);
}
.card-drawer-body {
  padding: 1.25rem;
}
.card-drawer-recent {
  border-top: 1px solid var(--color-border);
  padding: 1rem 1.25rem;
}
.card-drawer-recent-title {
  font-family: var(--font-ui);
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-text-secondary);
  margin-bottom: 0.625rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.card-drawer-recent-list {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
.recent-card-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.4375rem 0.625rem;
  border-radius: 0.5rem;
  background: var(--color-bg);
  font-size: 0.8125rem;
}
.recent-card-emotion {
  font-family: var(--font-ui);
  font-weight: 600;
  color: var(--color-accent);
  white-space: nowrap;
  min-width: 2.5rem;
}
.recent-card-summary {
  font-family: var(--font-diary);
  color: var(--color-text-primary);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.card-drawer-enter-active,
.card-drawer-leave-active {
  transition: opacity var(--motion-duration, 220ms) var(--motion-ease, ease);
}
.card-drawer-enter-active .card-drawer-panel,
.card-drawer-leave-active .card-drawer-panel {
  transition: transform var(--motion-duration, 220ms) var(--motion-ease, ease);
}
.card-drawer-enter-from,
.card-drawer-leave-to {
  opacity: 0;
}
.card-drawer-enter-from .card-drawer-panel {
  transform: translateY(1rem) scale(0.98);
}
.card-drawer-leave-to .card-drawer-panel {
  transform: translateY(0.5rem) scale(0.98);
}
</style>
