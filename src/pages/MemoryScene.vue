<script setup lang="ts">
import { computed, onActivated, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  PhBrain,
  PhStack,
  PhCards,
  PhArrowRight,
  PhSparkle,
  PhNotePencil,
  PhChartLineUp,
} from '@phosphor-icons/vue'

import GlassPanel from '@/shared/components/GlassPanel.vue'
import EpisodicEntryCard from '@/features/memory/EpisodicEntryCard.vue'
import MoodTrendChart from '@/features/memory/MoodTrendChart.vue'
import { memoryCopy as copy } from '@/shared/copy/memory'
import { useMemoryStore } from '@/stores/memory'
import { useCardStore } from '@/stores/card'
import type { EpisodicEntry, EpisodicEntryUpdate } from '@/shared/api/memory'

const router = useRouter()
const memoryStore = useMemoryStore()
const cardStore = useCardStore()

defineOptions({ name: 'MemoryScene' })

/** Randomly pick an element from an array. */
const pick = <T>(arr: readonly T[]): T => arr[Math.floor(Math.random() * arr.length)]

const subtitle = ref(pick(copy.subtitle))

const showDeleteConfirm = ref(false)
const pendingDeleteId = ref<string | null>(null)

const profile = computed(() => memoryStore.profile)
const overview = computed(() => memoryStore.overview)
const episodic = computed(() => memoryStore.episodic)
const cards = computed(() => cardStore.cards)

function formatTime(ts: number): string {
  const d = new Date(ts * 1000)
  return (
    d.toLocaleDateString('zh-CN') +
    ' ' +
    d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  )
}

function entrySourceLabel(entry: EpisodicEntry): string {
  return entry.source === 'card' ? copy.sourceCard : copy.sourceDiary
}

function goToCards() {
  router.push({ path: '/review', query: { mode: 'cards' } })
}

function goToDiary(diaryId: string) {
  router.push({ name: 'review-detail', params: { diaryId } })
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

onMounted(() => {
  void Promise.all([
    memoryStore.loadAll(),
    cardStore.loadCards(),
  ]).catch(() => {
    // surfaced via store errors
  })
})

onActivated(() => {
  void Promise.all([
    memoryStore.loadAll(),
    cardStore.loadCards(),
  ]).catch(() => {
    // surfaced via store errors
  })
})
</script>

<template>
  <main class="memory-scene">
    <header class="memory-scene__header">
      <h1 class="memory-scene__title">
        <PhBrain :size="20" weight="duotone" />
        {{ copy.title }}
      </h1>
    </header>

    <p class="memory-scene__subtitle">{{ subtitle }}</p>

    <p v-if="memoryStore.error" class="memory-scene__error">{{ memoryStore.error }}</p>

    <!-- ── Overview ─────────────────────────────────────────────── -->
    <GlassPanel v-if="overview" class="memory-scene__overview">
      <div class="memory-overview">
        <div class="memory-overview__stat">
          <span class="memory-overview__num">{{ overview.episodic_total }}</span>
          <span class="memory-overview__label">情节记忆</span>
        </div>
        <div class="memory-overview__stat">
          <span class="memory-overview__num">{{ overview.episodic_from_cards }}</span>
          <span class="memory-overview__label">来自卡片</span>
        </div>
        <div class="memory-overview__stat">
          <span class="memory-overview__num">{{ overview.episodic_from_diaries }}</span>
          <span class="memory-overview__label">来自日记</span>
        </div>
        <div class="memory-overview__stat">
          <span class="memory-overview__num">{{ overview.card_total }}</span>
          <span class="memory-overview__label">记忆卡片</span>
        </div>
      </div>
      <p class="memory-overview__profile">
        <PhSparkle :size="14" weight="fill" />
        {{ overview.profile_built ? copy.profileBuilt : copy.profileEmpty }}
      </p>
    </GlassPanel>

    <!-- ── Long-term profile ────────────────────────────────────── -->
    <section class="memory-scene__section">
      <h2 class="memory-scene__section-title">
        <PhBrain :size="16" weight="duotone" />
        {{ copy.profileTitle }}
      </h2>
      <p class="memory-scene__section-desc">{{ copy.profileDesc }}</p>

      <GlassPanel v-if="profile" class="memory-profile">
        <div class="memory-profile__row">
          <span class="memory-profile__key">{{ copy.personalityTags }}</span>
          <div v-if="profile.personality_tags.length" class="memory-profile__chips">
            <span v-for="tag in profile.personality_tags" :key="tag" class="memory-chip">{{ tag }}</span>
          </div>
          <span v-else class="memory-profile__none">{{ copy.none }}</span>
        </div>

        <div class="memory-profile__row">
          <span class="memory-profile__key">{{ copy.emotionBaseline }}</span>
          <div class="memory-profile__baseline">
            <span class="memory-baseline-item">
              {{ copy.dominantEmotion }}：{{ profile.emotion_baseline.dominant_emotion || copy.none }}
            </span>
            <span class="memory-baseline-item">
              {{ copy.avgSentiment }}：{{ (profile.emotion_baseline.average_sentiment * 100).toFixed(0) }}%
            </span>
            <span class="memory-baseline-item">
              {{ copy.volatility }}：{{ (profile.emotion_baseline.volatility * 100).toFixed(0) }}%
            </span>
          </div>
        </div>

        <div class="memory-profile__row">
          <span class="memory-profile__key">{{ copy.importantPeople }}</span>
          <div v-if="profile.important_people.length" class="memory-profile__chips">
            <span v-for="p in profile.important_people" :key="p.name" class="memory-chip">
              {{ p.name }}<template v-if="p.relation"> · {{ p.relation }}</template>
            </span>
          </div>
          <span v-else class="memory-profile__none">{{ copy.none }}</span>
        </div>

        <div class="memory-profile__row">
          <span class="memory-profile__key">{{ copy.recurringTopics }}</span>
          <div v-if="profile.recurring_topics.length" class="memory-profile__chips">
            <span v-for="t in profile.recurring_topics" :key="t" class="memory-chip">{{ t }}</span>
          </div>
          <span v-else class="memory-profile__none">{{ copy.none }}</span>
        </div>

        <div class="memory-profile__row">
          <span class="memory-profile__key">{{ copy.responseStyle }}</span>
          <span class="memory-profile__value">{{ profile.preferred_response_style || copy.none }}</span>
        </div>
      </GlassPanel>

      <div v-else-if="!memoryStore.loading" class="memory-scene__empty">
        <p class="memory-scene__empty-title">{{ copy.profileEmpty }}</p>
        <p class="memory-scene__empty-desc">{{ copy.profileEmptyHint }}</p>
      </div>
    </section>

    <!-- ── Mood trend chart ────────────────────────────────────── -->
    <section v-if="cards.length >= 2" class="memory-scene__section">
      <h2 class="memory-scene__section-title">
        <PhChartLineUp :size="16" weight="duotone" />
        {{ copy.emotionChartTitle }}
      </h2>
      <p class="memory-scene__section-desc">{{ copy.emotionChartDesc }}</p>
      <GlassPanel>
        <MoodTrendChart :cards="cards" />
      </GlassPanel>
    </section>

    <!-- ── Episodic timeline ────────────────────────────────────── -->
    <section class="memory-scene__section">
      <h2 class="memory-scene__section-title">
        <PhStack :size="16" weight="duotone" />
        {{ copy.episodicTitle }}
      </h2>
      <p class="memory-scene__section-desc">{{ copy.episodicDesc }}</p>

      <div v-if="episodic.length" class="memory-timeline">
        <EpisodicEntryCard
          v-for="entry in episodic"
          :key="entry.entry_id"
          :entry="entry"
          :source-label="entrySourceLabel(entry)"
          :formatted-time="formatTime(entry.timestamp)"
          :saving="memoryStore.saving"
          @save="onSaveEntry"
          @delete="onAskDelete"
          @view-diary="goToDiary"
        />
      </div>

      <div v-else-if="!memoryStore.loading" class="memory-scene__empty">
        <p class="memory-scene__empty-title">{{ copy.episodicEmpty }}</p>
        <p class="memory-scene__empty-desc">{{ copy.episodicEmptyHint }}</p>
      </div>
    </section>

    <!-- ── Cards management entry ───────────────────────────────── -->
    <section class="memory-scene__section">
      <h2 class="memory-scene__section-title">
        <PhCards :size="16" weight="duotone" />
        {{ copy.cardsTitle }}
      </h2>
      <p class="memory-scene__section-desc">{{ copy.cardsDesc }}</p>
      <GlassPanel class="memory-cards-link" @click="goToCards">
        <div class="memory-cards-link__body">
          <PhNotePencil :size="22" weight="duotone" />
          <span>{{ copy.goToCards }}</span>
        </div>
        <PhArrowRight :size="18" />
      </GlassPanel>
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
  padding: 1.25rem 1rem 2.5rem;
}

.memory-scene__header {
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 0.75rem;
}

.memory-scene__title {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.memory-scene__subtitle {
  text-align: center;
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  margin-bottom: 1.25rem;
}

.memory-scene__error {
  padding: 0.75rem 1rem;
  border-radius: 0.625rem;
  background: color-mix(in srgb, var(--color-danger) 12%, transparent);
  color: var(--color-danger);
  font-size: 0.875rem;
  margin-bottom: 1rem;
}

/* ── Overview ───────────────────────────────────────────────── */
.memory-scene__overview {
  margin-bottom: 1.75rem;
}

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
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--color-accent);
}

.memory-overview__label {
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
}

.memory-overview__profile {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.375rem;
  margin-top: 0.875rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--color-border);
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

/* ── Section ────────────────────────────────────────────────── */
.memory-scene__section {
  margin-bottom: 1.75rem;
}

.memory-scene__section-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 0.25rem;
}

.memory-scene__section-desc {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  margin-bottom: 0.875rem;
}

/* ── Profile ────────────────────────────────────────────────── */
.memory-profile {
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
}

.memory-profile__row {
  display: flex;
  flex-direction: column;
  gap: 0.4375rem;
}

.memory-profile__key {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-accent);
}

.memory-profile__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
}

.memory-profile__baseline {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
}

.memory-baseline-item {
  font-size: 0.8125rem;
  color: var(--color-text-primary);
}

.memory-chip {
  display: inline-flex;
  align-items: center;
  padding: 0.1875rem 0.625rem;
  border-radius: 1rem;
  font-size: 0.75rem;
  color: var(--color-text-primary);
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
}

.memory-profile__value {
  font-size: 0.8125rem;
  color: var(--color-text-primary);
}

.memory-profile__none {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  opacity: 0.7;
}

/* ── Timeline ───────────────────────────────────────────────── */
.memory-timeline {
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}

.memory-confirm-overlay {
  position: fixed;
  inset: 0;
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.35);
  backdrop-filter: blur(4px);
}

.memory-confirm-dialog {
  width: min(20rem, calc(100vw - 2rem));
  padding: 1.5rem;
  border-radius: var(--radius-outer);
  border: 1px solid var(--color-border);
  background: var(--color-bg-elevated);
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
  border-radius: 0.5rem;
  border: 1px solid var(--color-border);
  font-size: 0.8125rem;
  cursor: pointer;
  background: var(--color-bg-elevated);
  color: var(--color-text-secondary);
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

/* ── Empty ──────────────────────────────────────────────────── */
.memory-scene__empty {
  text-align: center;
  padding: 1.75rem 1.5rem;
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-button, 0.75rem);
}

.memory-scene__empty-title {
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 0.375rem;
}

.memory-scene__empty-desc {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  max-width: 24rem;
  margin: 0 auto;
}

/* ── Cards link ─────────────────────────────────────────────── */
.memory-cards-link {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  transition: border-color var(--motion-duration, 220ms) var(--motion-ease, ease);
}

.memory-cards-link:hover {
  border-color: var(--color-accent);
}

.memory-cards-link__body {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text-primary);
}
</style>
