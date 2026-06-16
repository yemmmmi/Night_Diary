<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { PhArrowLeft, PhTrash } from '@phosphor-icons/vue'

import GameButton from '@/shared/components/GameButton.vue'
import GlassPanel from '@/shared/components/GlassPanel.vue'
import AITypingIndicator from '@/shared/components/AITypingIndicator.vue'
import { weeklyCopy as copy } from '@/shared/copy/weekly'
import type { WeeklyReport } from '@/shared/api/weekly'
import { useWeeklyStore } from '@/stores/weekly'
import { startOfWeekMonday, toIsoDate } from '@/shared/utils/diaryFormat'

const router = useRouter()
const weeklyStore = useWeeklyStore()

const selectedId = ref<number | null>(null)
const showDeleteConfirm = ref(false)
const pendingDeleteId = ref<number | null>(null)

const thisWeekStartIso = computed(() => toIsoDate(startOfWeekMonday(new Date(), 0)))

const hasThisWeek = computed(() =>
  weeklyStore.reports.some((r) => r.period_start === thisWeekStartIso.value),
)

const selected = computed<WeeklyReport | null>(() => {
  if (selectedId.value != null) {
    return weeklyStore.reports.find((r) => r.id === selectedId.value) ?? null
  }
  return weeklyStore.latest
})

function formatPeriod(report: WeeklyReport): string {
  const fmt = (iso: string) => {
    const [, m, d] = iso.split('-')
    return `${Number(m)}月${Number(d)}日`
  }
  return `${fmt(report.period_start)} - ${fmt(report.period_end)}`
}

async function load() {
  try {
    await weeklyStore.loadReports()
  } catch {
    // surfaced via weeklyStore.error
  }
}

async function onGenerate() {
  try {
    const report = await weeklyStore.generate()
    selectedId.value = report.id
  } catch {
    // surfaced via weeklyStore.error
  }
}

async function onRegenerate() {
  try {
    const report = await weeklyStore.regenerate()
    selectedId.value = report.id
  } catch {
    // surfaced via weeklyStore.error
  }
}

function selectReport(report: WeeklyReport) {
  selectedId.value = report.id
}

function askDelete(report: WeeklyReport) {
  pendingDeleteId.value = report.id
  showDeleteConfirm.value = true
}

async function onDeleteConfirm() {
  const id = pendingDeleteId.value
  showDeleteConfirm.value = false
  pendingDeleteId.value = null
  if (id == null) return
  try {
    await weeklyStore.remove(id)
    if (selectedId.value === id) selectedId.value = null
  } catch {
    // surfaced via weeklyStore.error
  }
}

function goBack() {
  router.push('/')
}

onMounted(() => {
  void load()
})
</script>

<template>
  <main class="weekly-scene">
    <header class="weekly-scene__header">
      <GameButton variant="ghost" @click="goBack">
        <PhArrowLeft :size="16" />
        {{ copy.back }}
      </GameButton>
      <h1 class="weekly-scene__title">{{ copy.title }}</h1>
      <span class="weekly-scene__spacer" />
    </header>

    <p class="weekly-scene__subtitle">{{ copy.subtitle }}</p>

    <p v-if="weeklyStore.error" class="weekly-scene__error">{{ weeklyStore.error }}</p>

    <div class="weekly-scene__actions">
      <GameButton
        v-if="!hasThisWeek"
        variant="primary"
        class="glow-pulse"
        :disabled="weeklyStore.generating"
        @click="onGenerate"
      >
        {{ weeklyStore.generating ? copy.generating : copy.generate }}
      </GameButton>
      <GameButton
        v-else
        variant="secondary"
        :disabled="weeklyStore.generating"
        @click="onRegenerate"
      >
        {{ weeklyStore.generating ? copy.generating : copy.regenerate }}
      </GameButton>
    </div>

    <div v-if="weeklyStore.generating" class="weekly-scene__typing">
      <AITypingIndicator :label="copy.generating" />
    </div>

    <GlassPanel v-if="selected" elevated class="weekly-scene__panel">
      <div class="weekly-card__meta">
        <span class="weekly-card__period">{{ formatPeriod(selected) }}</span>
        <span class="weekly-card__counts">
          {{ copy.diaryCount(selected.diary_count) }} · {{ copy.cardCount(selected.card_count) }}
        </span>
      </div>
      <p class="weekly-card__content">{{ selected.content }}</p>
    </GlassPanel>

    <section
      v-else-if="!weeklyStore.loading && !weeklyStore.generating"
      class="weekly-scene__empty"
    >
      <p class="weekly-scene__empty-title">{{ copy.empty }}</p>
      <p class="weekly-scene__empty-desc">{{ copy.emptyHint }}</p>
    </section>

    <section v-if="weeklyStore.reports.length > 1" class="weekly-scene__history">
      <p class="weekly-scene__history-title">{{ copy.historyTitle }}</p>
      <ul class="weekly-history__list">
        <li
          v-for="report in weeklyStore.reports"
          :key="report.id"
          class="weekly-history__item"
          :class="{ 'is-active': selected?.id === report.id }"
        >
          <button type="button" class="weekly-history__btn" @click="selectReport(report)">
            <span class="weekly-history__period">{{ formatPeriod(report) }}</span>
            <span class="weekly-history__counts">
              {{ copy.diaryCount(report.diary_count) }} · {{ copy.cardCount(report.card_count) }}
            </span>
          </button>
          <button
            type="button"
            class="weekly-history__delete"
            :aria-label="copy.delete"
            @click="askDelete(report)"
          >
            <PhTrash :size="15" />
          </button>
        </li>
      </ul>
    </section>

    <Teleport to="body">
      <div
        v-if="showDeleteConfirm"
        class="confirm-overlay"
        @click.self="showDeleteConfirm = false"
      >
        <div class="confirm-dialog">
          <p class="confirm-dialog__title">{{ copy.deleteConfirm }}</p>
          <p class="confirm-dialog__desc">{{ copy.deleteConfirmDesc }}</p>
          <div class="confirm-dialog__actions">
            <GameButton variant="secondary" @click="showDeleteConfirm = false">
              {{ copy.cancel }}
            </GameButton>
            <GameButton variant="primary" @click="onDeleteConfirm">
              {{ copy.confirmDelete }}
            </GameButton>
          </div>
        </div>
      </div>
    </Teleport>
  </main>
</template>

<style scoped>
.weekly-scene {
  min-height: calc(100vh - 2.5rem);
  max-width: 42rem;
  margin: 0 auto;
  padding: 1.25rem 1rem 2rem;
}

.weekly-scene__header {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}

.weekly-scene__title {
  text-align: center;
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.weekly-scene__spacer {
  width: 4.5rem;
}

.weekly-scene__subtitle {
  text-align: center;
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  margin-bottom: 1.25rem;
}

.weekly-scene__error {
  padding: 0.75rem 1rem;
  border-radius: 0.625rem;
  background: color-mix(in srgb, var(--color-danger) 12%, transparent);
  color: var(--color-danger);
  font-size: 0.875rem;
  margin-bottom: 1rem;
}

.weekly-scene__actions {
  display: flex;
  justify-content: center;
  margin-bottom: 1rem;
}

.weekly-scene__typing {
  display: flex;
  justify-content: center;
  margin-bottom: 1rem;
}

.weekly-scene__panel {
  margin-bottom: 1.5rem;
}

.weekly-card__meta {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
  padding-bottom: 0.625rem;
  border-bottom: 1px solid var(--color-border);
}

.weekly-card__period {
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.weekly-card__counts {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

.weekly-card__content {
  font-family: var(--font-diary);
  font-size: 0.9375rem;
  line-height: 1.85;
  color: var(--color-text-primary);
  white-space: pre-wrap;
}

.weekly-scene__empty {
  text-align: center;
  padding: 2.5rem 1.5rem;
}

.weekly-scene__empty-title {
  font-size: 1.0625rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 0.5rem;
}

.weekly-scene__empty-desc {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  max-width: 22rem;
  margin: 0 auto;
}

.weekly-scene__history-title {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 0.625rem;
}

.weekly-history__list {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  list-style: none;
  padding: 0;
  margin: 0;
}

.weekly-history__item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  border: 1px solid var(--color-border);
  border-radius: 0.625rem;
  background: var(--color-bg-elevated);
  padding: 0.125rem 0.375rem 0.125rem 0;
}

.weekly-history__item.is-active {
  border-color: var(--color-accent-muted);
}

.weekly-history__btn {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.125rem;
  text-align: left;
  border: none;
  background: transparent;
  cursor: pointer;
  padding: 0.5rem 0.75rem;
}

.weekly-history__period {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.weekly-history__counts {
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
}

.weekly-history__delete {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  border-radius: 0.5rem;
}

.weekly-history__delete:hover {
  color: var(--color-danger);
}

.confirm-overlay {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.35);
  backdrop-filter: blur(4px);
}

.confirm-dialog {
  width: min(20rem, calc(100vw - 2rem));
  padding: 1.5rem;
  border-radius: var(--radius-outer);
  border: 1px solid var(--color-border);
  background: var(--color-bg-elevated);
  text-align: center;
}

.confirm-dialog__title {
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 0.375rem;
}

.confirm-dialog__desc {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  margin-bottom: 1rem;
}

.confirm-dialog__actions {
  display: flex;
  justify-content: center;
  gap: 0.75rem;
}
</style>
