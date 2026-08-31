<script setup lang="ts">
import { computed, onActivated, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import CardsSection from '@/features/memory/CardsSection.vue'
import EpisodicEntryCard from '@/features/memory/EpisodicEntryCard.vue'
import MoodTrendChart from '@/features/memory/MoodTrendChart.vue'
import WeeklyLetterCard from '@/features/timeline/WeeklyLetterCard.vue'
import { memoryCopy as copy } from '@/shared/copy/memory'
import { useMemoryStore } from '@/stores/memory'
import { useCardStore } from '@/stores/card'
import { useWeeklyStore } from '@/stores/weekly'
import { getMoodTrends, type MoodTrendPoint } from '@/shared/api/card'
import type { EpisodicEntry, EpisodicEntryUpdate } from '@/shared/api/memory'
import {
  startOfWeekMonday,
  toIsoDate,
} from '@/shared/utils/diaryFormat'
import { chineseDateLabel } from '@/shared/utils/todayFormat'

defineOptions({ name: 'MemoryScene' })

/** 洞悉页最近保留的周记信笺数。 */
const WEEKLY_LETTER_COUNT = 4
/** 情绪趋势窗口：服务端 getMoodTrends 的 days 参数与细柱格数一致。 */
const TREND_DAYS = 14

const router = useRouter()
const memoryStore = useMemoryStore()
const cardStore = useCardStore()
const weeklyStore = useWeeklyStore()

/** Randomly pick an element from an array. */
const pick = <T>(arr: readonly T[]): T => arr[Math.floor(Math.random() * arr.length)]

const subtitle = ref(pick(copy.subtitle))

const showDeleteConfirm = ref(false)
const pendingDeleteId = ref<string | null>(null)

const profile = computed(() => memoryStore.profile)
const overview = computed(() => memoryStore.overview)
const episodic = computed(() => memoryStore.episodic)

// ── 情绪趋势（后端聚合，前端补零在 MoodTrendChart 内完成） ────────
const trendPoints = ref<MoodTrendPoint[]>([])
const trendLoaded = ref(false)
const hasTrendData = computed(() => trendPoints.value.some((p) => p.card_count > 0))

async function loadTrend(): Promise<void> {
  try {
    trendPoints.value = await getMoodTrends({ days: TREND_DAYS })
  } catch {
    trendPoints.value = []
  } finally {
    trendLoaded.value = true
  }
}

// ── 周记信笺 ─────────────────────────────────────────────────────
const currentWeekIso = toIsoDate(startOfWeekMonday(new Date()))

/** 最近 4 封；本周尚未生成时补一封空信笺，留住生成入口。 */
const weeklyLetters = computed<string[]>(() => {
  const starts = weeklyStore.reports.slice(0, WEEKLY_LETTER_COUNT).map((r) => r.period_start)
  if (!starts.includes(currentWeekIso)) starts.unshift(currentWeekIso)
  return starts
})

// ── 长期画像的账簿式行文案 ────────────────────────────────────────
const baselineLabel = computed(() => {
  const baseline = profile.value?.emotion_baseline
  if (!baseline) return copy.none
  return [
    `${copy.dominantEmotion} ${baseline.dominant_emotion || copy.none}`,
    `${copy.avgSentiment} ${(baseline.average_sentiment * 100).toFixed(0)}%`,
    `${copy.volatility} ${(baseline.volatility * 100).toFixed(0)}%`,
  ].join(' · ')
})

const peopleLabel = computed(() => {
  const people = profile.value?.important_people ?? []
  if (!people.length) return copy.none
  return people.map((p) => (p.relation ? `${p.name}（${p.relation}）` : p.name)).join('、')
})

const topicsLabel = computed(() => {
  const topics = profile.value?.recurring_topics ?? []
  return topics.length ? topics.join('、') : copy.none
})

// ── 情节记忆 ─────────────────────────────────────────────────────
/** 时间戳用中文日期 + 时分（细线行账簿小字）。 */
function formatTime(entry: EpisodicEntry): string {
  const date = new Date(entry.timestamp * 1000)
  const hh = String(date.getHours()).padStart(2, '0')
  const mm = String(date.getMinutes()).padStart(2, '0')
  const label = chineseDateLabel(toIsoDate(date))
  return label ? `${label} ${hh}:${mm}` : `${hh}:${mm}`
}

function entrySourceLabel(entry: EpisodicEntry): string {
  return entry.source === 'card' ? copy.sourceCard : copy.sourceDiary
}

function goToDiary(diaryId: string) {
  router.push(`/write/${diaryId}`)
}

function onAskDelete(entryId: string) {
  pendingDeleteId.value = entryId
  showDeleteConfirm.value = true
}

async function onDeleteConfirm() {
  const id = pendingDeleteId.value
  showDeleteConfirm.value = false
  pendingDeleteId.value = null
  if (id) await memoryStore.removeEpisodic(id)
}

async function onSaveEntry(entryId: string, patch: EpisodicEntryUpdate) {
  await memoryStore.saveEpisodic(entryId, patch)
}

// ── 加载：keep-alive 下首次挂载会连发 onMounted + onActivated ──────
async function refresh(): Promise<void> {
  await Promise.all([
    memoryStore.loadAll(),
    cardStore.loadCards(),
    loadTrend(),
    weeklyStore.loadReports(WEEKLY_LETTER_COUNT),
  ]).catch(() => {
    // surfaced via store errors
  })
}

/** 首次挂载只走 onMounted 一次；其后每次回到本页由 onActivated 刷新。 */
let firstLoad = true

onMounted(() => {
  void refresh()
})

onActivated(() => {
  if (firstLoad) {
    firstLoad = false
    return
  }
  void refresh()
})
</script>

<template>
  <main class="memory-scene">
    <header class="memory-head">
      <h1 class="memory-head__title">{{ copy.title }}</h1>
      <p class="memory-head__subtitle">{{ subtitle }}</p>
    </header>

    <p v-if="memoryStore.error" class="memory-error">{{ memoryStore.error }}</p>

    <!-- ── 情绪趋势：14 天细柱 ─────────────────────────────────── -->
    <section class="memory-section">
      <h2 class="memory-section__title">{{ copy.emotionChartTitle }}</h2>
      <p class="memory-section__desc">{{ copy.emotionChartDesc }}</p>
      <MoodTrendChart :points="trendPoints" :days="TREND_DAYS" />
      <p v-if="trendLoaded && !hasTrendData" class="memory-blank__hint">
        {{ copy.emotionChartEmpty }}
      </p>
    </section>

    <!-- ── 概览统计：一行四组账簿数字 ───────────────────────────── -->
    <section v-if="overview" class="memory-section">
      <h2 class="memory-section__title">{{ copy.overviewTitle }}</h2>
      <div class="memory-overview">
        <div class="memory-overview__stat" data-testid="memory-stat">
          <span class="memory-overview__num">{{ overview.episodic_total }}</span>
          <span class="memory-overview__label">{{ copy.statEpisodic }}</span>
        </div>
        <div class="memory-overview__stat" data-testid="memory-stat">
          <span class="memory-overview__num">{{ overview.episodic_from_cards }}</span>
          <span class="memory-overview__label">{{ copy.statFromCards }}</span>
        </div>
        <div class="memory-overview__stat" data-testid="memory-stat">
          <span class="memory-overview__num">{{ overview.episodic_from_diaries }}</span>
          <span class="memory-overview__label">{{ copy.statFromDiaries }}</span>
        </div>
        <div class="memory-overview__stat" data-testid="memory-stat">
          <span class="memory-overview__num">{{ overview.card_total }}</span>
          <span class="memory-overview__label">{{ copy.statCards }}</span>
        </div>
      </div>
      <p class="memory-overview__profile">
        {{ overview.profile_built ? copy.profileBuilt : copy.profileEmpty }}
      </p>
    </section>

    <!-- ── 长期画像：key-value 细线行 ──────────────────────────── -->
    <section class="memory-section">
      <h2 class="memory-section__title">{{ copy.profileTitle }}</h2>
      <p class="memory-section__desc">{{ copy.profileDesc }}</p>

      <div v-if="profile" class="memory-profile">
        <div class="memory-profile__row">
          <span class="memory-profile__key">{{ copy.personalityTags }}</span>
          <span class="memory-profile__value">
            {{ profile.personality_tags.length ? profile.personality_tags.join('、') : copy.none }}
          </span>
        </div>
        <div class="memory-profile__row">
          <span class="memory-profile__key">{{ copy.emotionBaseline }}</span>
          <span class="memory-profile__value">{{ baselineLabel }}</span>
        </div>
        <div class="memory-profile__row">
          <span class="memory-profile__key">{{ copy.importantPeople }}</span>
          <span class="memory-profile__value">{{ peopleLabel }}</span>
        </div>
        <div class="memory-profile__row">
          <span class="memory-profile__key">{{ copy.recurringTopics }}</span>
          <span class="memory-profile__value">{{ topicsLabel }}</span>
        </div>
        <div class="memory-profile__row">
          <span class="memory-profile__key">{{ copy.responseStyle }}</span>
          <span class="memory-profile__value">{{ profile.preferred_response_style || copy.none }}</span>
        </div>
      </div>

      <div v-else-if="!memoryStore.loading" class="memory-blank">
        <p class="memory-blank__title">{{ copy.profileEmpty }}</p>
        <p class="memory-blank__hint">{{ copy.profileEmptyHint }}</p>
      </div>
    </section>

    <!-- ── 情节记忆：细线行 ────────────────────────────────────── -->
    <section class="memory-section">
      <h2 class="memory-section__title">{{ copy.episodicTitle }}</h2>
      <p class="memory-section__desc">{{ copy.episodicDesc }}</p>

      <div v-if="episodic.length" class="memory-episodic">
        <EpisodicEntryCard
          v-for="entry in episodic"
          :key="entry.entry_id"
          :entry="entry"
          :source-label="entrySourceLabel(entry)"
          :formatted-time="formatTime(entry)"
          :saving="memoryStore.saving"
          @save="onSaveEntry"
          @delete="onAskDelete"
          @view-diary="goToDiary"
        />
      </div>

      <div v-else-if="!memoryStore.loading" class="memory-blank">
        <p class="memory-blank__title">{{ copy.episodicEmpty }}</p>
        <p class="memory-blank__hint">{{ copy.episodicEmptyHint }}</p>
      </div>
    </section>

    <!-- ── 记忆卡片：细线行 ────────────────────────────────────── -->
    <section class="memory-section">
      <h2 class="memory-section__title">{{ copy.cardsTitle }}</h2>
      <p class="memory-section__desc">{{ copy.cardsDesc }}</p>
      <CardsSection />
    </section>

    <!-- ── 周记信笺 ────────────────────────────────────────────── -->
    <section class="memory-section">
      <h2 class="memory-section__title">{{ copy.weeklyTitle }}</h2>
      <p class="memory-section__desc">{{ copy.weeklyDesc }}</p>
      <div class="memory-weekly">
        <WeeklyLetterCard
          v-for="startIso in weeklyLetters"
          :key="startIso"
          :week-start-iso="startIso"
          :autoload="false"
        />
      </div>
    </section>
  </main>

  <Teleport to="body">
    <div
      v-if="showDeleteConfirm"
      class="memory-confirm-overlay"
      @click.self="showDeleteConfirm = false"
    >
      <div class="memory-confirm-dialog">
        <p class="memory-confirm-dialog__title">{{ copy.confirmDeleteTitle }}</p>
        <p class="memory-confirm-dialog__desc">{{ copy.confirmDeleteDesc }}</p>
        <div class="memory-confirm-dialog__actions">
          <button
            type="button"
            class="memory-confirm-dialog__btn"
            @click="showDeleteConfirm = false"
          >
            {{ copy.cancel }}
          </button>
          <button
            type="button"
            class="memory-confirm-dialog__btn memory-confirm-dialog__btn--danger"
            :disabled="memoryStore.saving"
            @click="onDeleteConfirm"
          >
            {{ copy.confirmDelete }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.memory-scene {
  min-height: calc(100vh - 2.5rem);
  max-width: 44rem;
  margin: 0 auto;
  padding: 1.75rem 1.5rem 2.5rem;
}

/* ── 页头 ────────────────────────────────────────────────────── */
.memory-head {
  text-align: center;
  margin-bottom: 1.75rem;
}

.memory-head__title {
  font-family: var(--font-display);
  font-size: 1.25rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: var(--color-text-primary);
  margin: 0;
}

.memory-head__subtitle {
  margin: 0.5rem 0 0;
  font-size: 0.8125rem;
  color: var(--color-text-faint);
  letter-spacing: 0.04em;
}

.memory-error {
  padding: 0.75rem 1rem;
  border-radius: var(--radius-seal);
  background: color-mix(in srgb, var(--color-danger) 12%, transparent);
  color: var(--color-danger);
  font-size: 0.8125rem;
  margin-bottom: 1rem;
}

/* ── 细线分节 ────────────────────────────────────────────────── */
.memory-section {
  border-top: 1px solid var(--color-line);
  padding-top: 1.25rem;
  margin-bottom: 2rem;
}

.memory-section__title {
  font-family: var(--font-ui);
  font-size: 0.8125rem;
  font-weight: 600;
  letter-spacing: 0.12em;
  color: var(--color-text-secondary);
  margin: 0 0 0.375rem;
}

.memory-section__desc {
  font-size: 0.75rem;
  color: var(--color-text-faint);
  margin: 0 0 0.875rem;
  line-height: 1.7;
}

/* ── 概览：一行四组账簿数字 ──────────────────────────────────── */
.memory-overview {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0.75rem;
}

.memory-overview__stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
}

.memory-overview__num {
  font-family: var(--font-display);
  font-size: 1.5rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--color-text-primary);
}

.memory-overview__label {
  font-size: 0.6875rem;
  letter-spacing: 0.04em;
  color: var(--color-text-faint);
}

.memory-overview__profile {
  margin: 0.875rem 0 0;
  font-size: 0.75rem;
  color: var(--color-text-faint);
  text-align: center;
}

/* ── 长期画像：key-value 细线行 ─────────────────────────────── */
.memory-profile__row {
  display: grid;
  grid-template-columns: 8rem minmax(0, 1fr);
  gap: 1rem;
  align-items: baseline;
  padding: 0.625rem 0;
  border-bottom: 1px solid var(--color-line);
}

.memory-profile__row:last-child {
  border-bottom: none;
}

.memory-profile__key {
  font-size: 0.75rem;
  letter-spacing: 0.04em;
  color: var(--color-text-secondary);
}

.memory-profile__value {
  font-size: 0.875rem;
  line-height: 1.7;
  color: var(--color-text-primary);
}

/* ── 空态：淡墨提示 ─────────────────────────────────────────── */
.memory-blank {
  padding: 0.5rem 0;
}

.memory-blank__title {
  margin: 0;
  font-size: 0.875rem;
  color: var(--color-text-faint);
}

.memory-blank__hint {
  margin: 0.375rem 0 0;
  font-size: 0.75rem;
  line-height: 1.7;
  color: var(--color-text-faint);
  opacity: 0.85;
}

/* ── 情节记忆 / 周记列表 ────────────────────────────────────── */
.memory-episodic {
  display: flex;
  flex-direction: column;
}

.memory-weekly {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

/* ── 删除确认 ────────────────────────────────────────────────── */
.memory-confirm-overlay {
  position: fixed;
  inset: 0;
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.35);
}

.memory-confirm-dialog {
  width: min(20rem, calc(100vw - 2rem));
  padding: 1.5rem;
  border-radius: var(--radius-outer);
  border: 1px solid var(--color-line);
  background: var(--color-surface-raised);
  box-shadow: var(--shadow-panel);
  text-align: center;
}

.memory-confirm-dialog__title {
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 0.375rem;
}

.memory-confirm-dialog__desc {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  margin-bottom: 1rem;
}

.memory-confirm-dialog__actions {
  display: flex;
  justify-content: center;
  gap: 0.75rem;
}

.memory-confirm-dialog__btn {
  padding: 0.4375rem 1rem;
  border-radius: var(--radius-button);
  border: 1px solid var(--color-line);
  font-size: 0.8125rem;
  cursor: pointer;
  background: transparent;
  color: var(--color-text-secondary);
  transition: color var(--dur-fast) var(--ease-out-quart);
}

.memory-confirm-dialog__btn--danger {
  background: var(--color-danger);
  border-color: var(--color-danger);
  color: #fff;
  font-weight: 600;
}

.memory-confirm-dialog__btn:disabled {
  opacity: 0.5;
  cursor: default;
}

@media (max-width: 560px) {
  .memory-overview {
    grid-template-columns: repeat(2, 1fr);
    row-gap: 1.25rem;
  }

  .memory-profile__row {
    grid-template-columns: 1fr;
    gap: 0.25rem;
  }
}
</style>
