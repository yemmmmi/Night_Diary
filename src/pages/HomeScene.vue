<script setup lang="ts">
import { computed, onActivated, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PhCaretLeft, PhCaretRight, PhNotePencil } from '@phosphor-icons/vue'

defineOptions({ name: 'HomeScene' })

import BrandMark from '@/shared/components/BrandMark.vue'
import GameButton from '@/shared/components/GameButton.vue'
import { getStats, type AppStats } from '@/shared/api/stats'
import type { DiaryEntry } from '@/shared/api/diary'
import type { MemoryCard } from '@/shared/api/card'
import { homeSceneCopy as copy } from '@/shared/copy/homeScene'
import { cardCopy } from '@/shared/copy/card'
import { useDiaryStore } from '@/stores/diary'
import { useCardStore } from '@/stores/card'
import { useSettingsStore } from '@/stores/settings'
import MemoryCardInput from '@/features/card/MemoryCardInput.vue'
import EmotionChips from '@/features/card/EmotionChips.vue'
import {
  computeWritingStreak,
  diaryStatus,
  diaryStatusLabel,
  diarySummary,
  endOfWeekSunday,
  formatWeekRangeLabel,
  groupEntriesForWeek,
  startOfWeekMonday,
  toIsoDate,
  weekdayLabel,
} from '@/shared/utils/diaryFormat'

const router = useRouter()
const route = useRoute()
const diaryStore = useDiaryStore()
const cardStore = useCardStore()
const settings = useSettingsStore()

const weekOffset = ref(0)
const stats = ref<AppStats | null>(null)

const weekStart = computed(() => startOfWeekMonday(new Date(), weekOffset.value))
const weekEnd = computed(() => endOfWeekSunday(weekStart.value))
const weekLabel = computed(() => formatWeekRangeLabel(weekStart.value, weekEnd.value))

type KanbanItem =
  | { kind: 'diary'; entry: DiaryEntry; linkedCard: MemoryCard | null }
  | { kind: 'card'; card: MemoryCard }

function cardDateIso(card: MemoryCard): string {
  return card.created_at.slice(0, 10)
}

const weekColumns = computed(() => {
  const { dayColumns, inbox } = groupEntriesForWeek(
    diaryStore.entries,
    weekStart.value,
    weekEnd.value,
  )

  // Map: diary_id → linked MemoryCard (cards that have been expanded to diaries)
  const cardByDiaryId = new Map<number, MemoryCard>()
  const standaloneCardsByDate = new Map<string, MemoryCard[]>()

  for (const card of cardStore.cards) {
    if (card.diary_id != null) {
      cardByDiaryId.set(card.diary_id, card)
    } else {
      const date = cardDateIso(card)
      const arr = standaloneCardsByDate.get(date)
      if (arr) arr.push(card)
      else standaloneCardsByDate.set(date, [card])
    }
  }

  const days = Array.from({ length: 7 }, (_, index) => {
    const date = new Date(weekStart.value)
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
    items.sort((a, b) => {
      const at = a.kind === 'diary'
        ? (a.entry.created_at ?? '')
        : a.card.created_at
      const bt = b.kind === 'diary'
        ? (b.entry.created_at ?? '')
        : b.card.created_at
      return at.localeCompare(bt)
    })

    return {
      key: iso,
      label: weekdayLabel(date),
      dayNumber: date.getDate(),
      items,
    }
  })

  const inboxStandaloneCards: MemoryCard[] = []
  for (const card of standaloneCardsByDate.values()) {
    for (const c of card) inboxStandaloneCards.push(c)
  }
  // Only cards NOT already in the week range go to inbox
  inboxStandaloneCards.length = 0
  for (const card of cardStore.cards) {
    if (card.diary_id != null) continue
    const d = cardDateIso(card)
    const startIso = toIsoDate(weekStart.value)
    const endIso = toIsoDate(weekEnd.value)
    if (d < startIso || d > endIso) {
      inboxStandaloneCards.push(card)
    }
  }

  const inboxItems: KanbanItem[] = [
    ...inbox.map((e): KanbanItem => ({ kind: 'diary', entry: e, linkedCard: cardByDiaryId.get(e.id) ?? null })),
    ...inboxStandaloneCards.map((c): KanbanItem => ({ kind: 'card', card: c })),
  ]

  return [...days, { key: 'inbox', label: copy.inboxColumn, dayNumber: null, items: inboxItems }]
})

const streak = computed(() => computeWritingStreak(diaryStore.entries))

const replyCount = computed(() =>
  diaryStore.entries.filter((e) => e.ai_ans && e.ai_ans.trim()).length,
)

const todayIso = computed(() => toIsoDate(new Date()))

const hasTodayEntry = computed(() =>
  diaryStore.entries.some((e) => e.date === todayIso.value),
)

const isEmpty = computed(
  () => !diaryStore.loading && diaryStore.entries.length === 0 && cardStore.cards.length === 0,
)

const writeButtonLabel = computed(() =>
  hasTodayEntry.value ? copy.continueWriting : copy.writeDiary,
)

const footerStatsLabel = computed(() =>
  copy.footerStats(stats.value?.diary_count ?? '\u2014', stats.value?.analysis_count ?? '\u2014'),
)

function statusClass(status: ReturnType<typeof diaryStatus>) {
  return `kanban-card__chip--${status}`
}

function openEntry(entry: DiaryEntry) {
  router.push(`/write/${entry.id}`)
}

function openCard(card: MemoryCard) {
  if (card.diary_id) {
    router.push(`/write/${card.diary_id}`)
  } else {
    cardStore.expandCard(card.card_id).then((result) => {
      diaryStore.loadEntries()
      router.push(`/write/${result.diary_id}`)
    }).catch(() => { /* handled by store */ })
  }
}

function writeToday() {
  router.push({ path: '/write', query: { date: todayIso.value } })
}

function createForDate(isoDate: string | null) {
  if (isoDate) {
    router.push({ path: '/write', query: { date: isoDate } })
    return
  }
  router.push('/write')
}

async function refreshHome() {
  await Promise.all([diaryStore.loadEntries(), loadStats(), cardStore.loadCards()])
}

async function loadStats() {
  try {
    stats.value = await getStats()
  } catch {
    stats.value = null
  }
}

const EMOTION_COLORS: Record<string, string> = {
  '\u5f00\u5fc3': '#4CAF50',
  '\u5e73\u9759': '#607D8B',
  '\u611f\u6fc0': '#D4A574',
  '\u671f\u5f85': '#26A69A',
  '\u5174\u594b': '#FF9800',
  '\u7126\u8651': '#7E57C2',
  '\u75b2\u60eb': '#9E9E9E',
  '\u60b2\u4f24': '#5C6BC0',
  '\u8ff7\u832b': '#78909C',
  '\u6124\u6012': '#EF5350',
}

function cardEmotionColor(card: MemoryCard): string {
  return EMOTION_COLORS[card.emotion] ?? 'var(--color-accent)'
}

function cardTypeLabel(card: MemoryCard): string {
  if (card.card_type === 'quick') return '\u6781\u901f'
  if (card.card_type === 'guided') return '\u5f15\u5bfc'
  return '\u6807\u51c6'
}

onMounted(() => {
  void refreshHome()
})

onActivated(() => {
  void refreshHome()
})

watch(
  () => route.path,
  (path) => {
    if (path === '/') void refreshHome()
  },
)
</script>

<template>
  <main class="home-scene">
    <header class="home-scene__header">
      <div class="home-scene__brand">
        <BrandMark class="home-scene__mark" />
        <div class="home-scene__brand-text">
          <h1 class="home-scene__title">{{ copy.title }}</h1>
          <p class="home-scene__streak" v-if="streak > 0">{{ copy.streak(streak) }}</p>
        </div>
      </div>
      <div class="home-scene__header-actions">
        <GameButton variant="ghost" @click="cardStore.openDrawer()">
          <PhNotePencil :size="16" />
          {{ cardCopy.newCard }}
        </GameButton>
        <GameButton class="glow-pulse" @click="writeToday">
          {{ writeButtonLabel }}
        </GameButton>
      </div>
    </header>

    <div v-if="replyCount > 0" class="home-scene__companion">
      <p v-if="replyCount > 0">{{ copy.replyBanner(settings.replierHasName ? settings.replierName : '', replyCount) }}</p>
      <p v-if="!hasTodayEntry && !isEmpty" class="home-scene__nudge">{{ copy.nudge }}</p>
    </div>

    <section v-if="isEmpty" class="home-scene__empty">
      <p class="home-scene__empty-title">{{ copy.emptyTitle }}</p>
      <p class="home-scene__empty-desc">{{ copy.emptyDesc }}</p>
      <GameButton variant="primary" class="home-scene__empty-cta" @click="writeToday">
        {{ copy.emptyCta }}
      </GameButton>
    </section>

    <section v-if="!isEmpty" class="home-scene__week-nav">
      <button type="button" class="week-nav__btn" @click="weekOffset -= 1">
        <PhCaretLeft :size="14" />
        {{ copy.prevWeek }}
      </button>
      <span class="week-nav__label">{{ weekLabel }}</span>
      <button type="button" class="week-nav__btn" @click="weekOffset += 1">
        {{ copy.nextWeek }}
        <PhCaretRight :size="14" />
      </button>
    </section>

    <div v-if="diaryStore.error" class="home-scene__error-banner">
      <span>{{ diaryStore.error }}</span>
      <GameButton variant="ghost" @click="refreshHome">{{ copy.retry }}</GameButton>
    </div>

    <div v-if="!isEmpty" class="home-scene__kanban" :class="{ 'is-loading': diaryStore.loading }">
      <div v-for="column in weekColumns" :key="column.key" class="kanban-col">
        <div class="kanban-col__head">
          <span>{{ column.label }}</span>
          <span v-if="column.dayNumber != null" class="kanban-col__day">{{ column.dayNumber }}</span>
        </div>

        <template v-for="item in column.items" :key="item.kind === 'diary' ? `d-${item.entry.id}` : `c-${item.card.card_id}`">
          <!-- Diary entry card -->
          <button
            v-if="item.kind === 'diary'"
            type="button"
            class="kanban-card"
            @click="openEntry(item.entry)"
          >
            <!-- Embedded card chip (if card was expanded to this diary) -->
            <div v-if="item.linkedCard" class="kanban-card__embed">
              <EmotionChips
                :emotions="item.linkedCard.emotions"
                :emotion="item.linkedCard.emotion"
                :size="11"
              />
              <span class="kanban-card__embed-type">{{ cardTypeLabel(item.linkedCard) }}</span>
            </div>
            <span class="kanban-card__summary">{{ diarySummary(item.entry.content) }}</span>
            <span class="kanban-card__chip" :class="statusClass(diaryStatus(item.entry))">
              {{ diaryStatusLabel(diaryStatus(item.entry)) }}
            </span>
          </button>

          <!-- Memory card in kanban -->
          <button
            v-else
            type="button"
            class="kanban-card kanban-card--card"
            :style="{ borderLeftColor: cardEmotionColor(item.card) }"
            @click="openCard(item.card)"
          >
            <div class="kanban-card__card-head">
              <EmotionChips
                :emotions="item.card.emotions"
                :emotion="item.card.emotion"
                :size="11"
              />
              <span class="kanban-card__card-type">{{ cardTypeLabel(item.card) }}</span>
            </div>
            <span v-if="item.card.event_summary" class="kanban-card__summary">
              {{ item.card.event_summary.slice(0, 28) }}{{ item.card.event_summary.length > 28 ? '\u2026' : '' }}
            </span>
            <span v-else class="kanban-card__summary kanban-card__summary--muted">\u8bb0\u5f55\u4e86\u5fc3\u60c5</span>
          </button>
        </template>

        <button
          v-if="column.key !== 'inbox'"
          type="button"
          class="kanban-add"
          @click="createForDate(column.key)"
        >
          +
        </button>
      </div>
    </div>

    <div v-if="!isEmpty" class="home-scene__footer">
      <span class="home-scene__footer-stats">{{ footerStatsLabel }}</span>
    </div>

    <!-- Card drawer overlay -->
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
              <button
                type="button"
                class="card-drawer-close"
                @click="cardStore.closeDrawer()"
              >
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
              <p class="card-drawer-recent-title">\u6700\u8fd1\u8bb0\u5fc6\u5361\u7247</p>
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
                    {{ card.event_summary.slice(0, 40) }}{{ card.event_summary.length > 40 ? '\u2026' : '' }}
                  </span>
                  <span class="recent-card-type">
                    {{ cardTypeLabel(card) }}
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
.home-scene {
  min-height: calc(100vh - 2.5rem);
  padding: 1.25rem 1rem 1.5rem;
  max-width: 90rem;
  margin: 0 auto;
}

.home-scene__header {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
}
.home-scene__brand {
  display: flex;
  align-items: center;
  gap: 0.625rem;
}
.home-scene__mark {
  width: 1.75rem;
  height: 1.75rem;
  flex-shrink: 0;
}
.home-scene__brand-text {
  display: flex;
  flex-direction: column;
}
.home-scene__title {
  font-size: 1.75rem;
  font-weight: 700;
  color: var(--color-text-primary);
  line-height: 1.2;
}
.home-scene__streak {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  margin-top: 0.125rem;
}

.home-scene__header-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.home-scene__companion {
  margin-bottom: 0.875rem;
  padding: 0.625rem 0.875rem;
  border-radius: 0.75rem;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
}
.home-scene__nudge {
  margin-top: 0.25rem;
  color: var(--color-accent);
}

.home-scene__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem 1.5rem;
  text-align: center;
  min-height: 40vh;
}
.home-scene__empty-title {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--color-text-primary);
  margin-bottom: 0.5rem;
}
.home-scene__empty-desc {
  font-size: 0.875rem;
  color: var(--color-text-secondary);
  margin-bottom: 1.5rem;
  max-width: 20rem;
}
.home-scene__empty-cta {
  font-size: 0.9375rem;
}

.home-scene__week-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.875rem;
}
.week-nav__btn {
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
.week-nav__btn:hover {
  color: var(--color-text-primary);
}
.week-nav__label {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.home-scene__error-banner {
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

.home-scene__kanban.is-loading {
  opacity: 0.65;
  pointer-events: none;
}
.home-scene__kanban {
  display: flex;
  gap: 0.5rem;
  overflow-x: auto;
  padding-bottom: 0.5rem;
}
.kanban-col {
  min-width: 8.5rem;
  flex: 1;
  flex-shrink: 0;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: 0.875rem;
  padding: 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
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
.kanban-col__day {
  font-size: 0.875rem;
  color: var(--color-text-primary);
}
.kanban-card {
  width: 100%;
  text-align: left;
  border: 1px solid var(--color-border);
  border-left-width: 1px;
  border-left-style: solid;
  border-left-color: var(--color-border);
  border-radius: 0.625rem;
  background: var(--color-bg-elevated-2);
  padding: 0.5rem;
  cursor: pointer;
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

.kanban-card__card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.25rem;
}

/* Embedded card chip inside diary entry */
.kanban-card__embed {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  margin-bottom: 0.3125rem;
  padding: 0.1875rem 0.375rem;
  border-radius: 0.375rem;
  background: color-mix(in srgb, var(--color-accent) 8%, transparent);
  font-size: 0.625rem;
}

.kanban-card__embed-type {
  font-family: var(--font-ui);
  font-size: 0.5625rem;
  font-weight: 600;
  color: var(--color-accent);
  padding: 0.0625rem 0.3125rem;
  border-radius: 0.25rem;
  background: color-mix(in srgb, var(--color-accent) 12%, transparent);
}

.kanban-card__card-type {
  font-family: var(--font-ui);
  font-size: 0.5625rem;
  font-weight: 600;
  color: var(--color-text-secondary);
  padding: 0.0625rem 0.3125rem;
  border-radius: 0.25rem;
  background: var(--color-bg-elevated);
}

.kanban-card__summary {
  display: block;
  font-size: 0.75rem;
  line-height: 1.45;
  color: var(--color-text-primary);
}

.kanban-card__summary--muted {
  color: var(--color-text-secondary);
  font-style: italic;
}

.kanban-card__chip {
  display: inline-block;
  margin-top: 0.375rem;
  border-radius: 999px;
  padding: 0.125rem 0.45rem;
  font-size: 0.625rem;
  font-weight: 600;
}
.kanban-card__chip--reply {
  background: color-mix(in srgb, var(--color-success) 18%, transparent);
  color: var(--color-success);
}
.kanban-card__chip--pending {
  background: color-mix(in srgb, var(--color-warning) 18%, transparent);
  color: var(--color-warning);
}
.kanban-card__chip--draft {
  background: color-mix(in srgb, var(--color-accent) 14%, transparent);
  color: var(--color-accent-muted);
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

.home-scene__footer {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  margin-top: 1.25rem;
  padding-top: 0.625rem;
  border-top: 1px solid var(--color-border);
}
.home-scene__footer-stats {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

/* Card drawer */
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
  transition: background var(--motion-duration, 220ms);
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

.recent-card-type {
  font-family: var(--font-ui);
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
  padding: 0.125rem 0.4375rem;
  background: var(--color-bg-elevated-2);
  border-radius: 0.375rem;
}

/* Drawer transition */
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
