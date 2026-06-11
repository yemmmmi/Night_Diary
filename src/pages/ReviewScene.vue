<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PhArrowLeft, PhCalendarBlank, PhListBullets } from '@phosphor-icons/vue'

import CalendarView from '@/features/review/CalendarView.vue'
import TimelineView from '@/features/review/TimelineView.vue'
import GameButton from '@/shared/components/GameButton.vue'
import GlassPanel from '@/shared/components/GlassPanel.vue'
import type { DiaryEntry } from '@/shared/api/diary'
import { useDiaryStore } from '@/stores/diary'
import { formatApiError } from '@/shared/utils/apiError'
import { diaryStatus, diaryStatusLabel, diarySummary } from '@/shared/utils/diaryFormat'

type ReviewMode = 'calendar' | 'timeline'

const route = useRoute()
const router = useRouter()
const diaryStore = useDiaryStore()

const mode = ref<ReviewMode>('timeline')
const selectedDate = ref<string | null>(null)
const selectedEntry = ref<DiaryEntry | null>(null)
const showDeleteConfirm = ref(false)
const deleteError = ref<string | null>(null)

const entriesOnSelectedDate = computed(() => {
  if (!selectedDate.value) return []
  return diaryStore.entries.filter((e) => e.date === selectedDate.value)
})

const routeDiaryId = computed(() => {
  const raw = route.params.diaryId
  const parsed = Number(raw)
  return Number.isFinite(parsed) ? parsed : null
})

function selectEntry(entry: DiaryEntry) {
  selectedEntry.value = entry
  selectedDate.value = entry.date
  router.replace({ name: 'review-detail', params: { diaryId: entry.id } })
}

function selectDate(iso: string) {
  selectedDate.value = iso
  const matches = diaryStore.entries.filter((e) => e.date === iso)
  if (matches.length === 1) {
    selectEntry(matches[0])
    return
  }
  selectedEntry.value = matches[0] ?? null
  if (selectedEntry.value) {
    router.replace({ name: 'review-detail', params: { diaryId: selectedEntry.value.id } })
  } else {
    router.replace({ name: 'review' })
  }
}

function openWrite(entry: DiaryEntry) {
  router.push(`/write/${entry.id}`)
}

function openAnalysis(entry: DiaryEntry) {
  router.push(`/analysis/${entry.id}`)
}

async function executeDelete() {
  if (!selectedEntry.value) return
  showDeleteConfirm.value = false
  deleteError.value = null
  const id = selectedEntry.value.id
  try {
    await diaryStore.removeEntry(id)
    selectedEntry.value = null
    await router.replace({ name: 'review' })
  } catch (err) {
    deleteError.value = formatApiError(err, '删除日记失败')
  }
}

function goHome() {
  router.push('/')
}

function syncFromRoute() {
  if (!routeDiaryId.value) {
    selectedEntry.value = null
    return
  }
  const found = diaryStore.entries.find((e) => e.id === routeDiaryId.value)
  if (found) {
    selectedEntry.value = found
    selectedDate.value = found.date
  }
}

onMounted(async () => {
  await diaryStore.loadEntries()
  syncFromRoute()
})

watch(
  () => route.params.diaryId,
  () => {
    syncFromRoute()
  },
)
</script>

<template>
  <main class="review-scene">
    <header class="review-scene__header">
      <GameButton variant="ghost" @click="goHome">
        <PhArrowLeft :size="16" />
        首页
      </GameButton>
      <h1 class="review-scene__title">历史回顾</h1>
      <div class="review-scene__tabs">
        <button
          type="button"
          class="review-scene__tab"
          :class="{ 'is-active': mode === 'calendar' }"
          @click="mode = 'calendar'"
        >
          <PhCalendarBlank :size="16" />
          月历
        </button>
        <button
          type="button"
          class="review-scene__tab"
          :class="{ 'is-active': mode === 'timeline' }"
          @click="mode = 'timeline'"
        >
          <PhListBullets :size="16" />
          时间线
        </button>
      </div>
    </header>

    <p v-if="deleteError" class="review-scene__delete-error">{{ deleteError }}</p>

    <div class="review-scene__layout">
      <section class="review-scene__main">
        <CalendarView
          v-if="mode === 'calendar'"
          :entries="diaryStore.entries"
          :selected-date="selectedDate"
          @select-date="selectDate"
        />
        <TimelineView
          v-else
          :entries="diaryStore.entries"
          :selected-id="selectedEntry?.id ?? null"
          @select="selectEntry"
        />
      </section>

      <aside v-if="selectedEntry" class="review-scene__detail">
        <GlassPanel elevated>
          <p class="review-scene__detail-date">
            {{ selectedEntry.date ?? selectedEntry.created_at.slice(0, 10) }}
          </p>
          <p class="review-scene__detail-summary font-diary">
            {{ diarySummary(selectedEntry.content, 120) }}
          </p>
          <span class="review-scene__detail-chip">
            {{ diaryStatusLabel(diaryStatus(selectedEntry)) }}
          </span>
          <div class="review-scene__detail-actions">
            <GameButton variant="secondary" @click="openWrite(selectedEntry)">继续编辑</GameButton>
            <GameButton
              v-if="diaryStatus(selectedEntry) !== 'draft'"
              variant="primary"
              @click="openAnalysis(selectedEntry)"
            >
              {{ selectedEntry.ai_ans?.trim() ? '查看回信' : '获取 AI 回信' }}
            </GameButton>
            <GameButton
              variant="ghost"
              class="review-scene__delete-btn"
              @click="showDeleteConfirm = true"
            >
              删除日记
            </GameButton>
          </div>
        </GlassPanel>
      </aside>

      <aside v-else-if="mode === 'calendar' && selectedDate && entriesOnSelectedDate.length > 1" class="review-scene__detail">
        <GlassPanel elevated>
          <p class="review-scene__detail-date">{{ selectedDate }}</p>
          <p class="review-scene__multi-hint">这一天有多篇日记，请选择：</p>
          <button
            v-for="entry in entriesOnSelectedDate"
            :key="entry.id"
            type="button"
            class="review-scene__multi-item"
            @click="selectEntry(entry)"
          >
            {{ diarySummary(entry.content) }}
          </button>
        </GlassPanel>
      </aside>
    </div>

    <Teleport to="body">
      <div
        v-if="showDeleteConfirm"
        class="confirm-overlay"
        @click.self="showDeleteConfirm = false"
      >
        <GlassPanel elevated class="confirm-dialog">
          <p class="confirm-dialog__title">确定删除这篇日记吗？</p>
          <p class="confirm-dialog__desc">日记内容及关联的 AI 回信将被永久删除，此操作不可撤销。</p>
          <div class="confirm-dialog__actions">
            <GameButton variant="secondary" @click="showDeleteConfirm = false">取消</GameButton>
            <GameButton variant="primary" class="confirm-dialog__danger-btn" @click="executeDelete">
              确认删除
            </GameButton>
          </div>
        </GlassPanel>
      </div>
    </Teleport>
  </main>
</template>

<style scoped>
.review-scene {
  min-height: calc(100vh - 2.5rem);
  max-width: 56rem;
  margin: 0 auto;
  padding: 1.25rem 1rem 2rem;
}

.review-scene__header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1.25rem;
}

.review-scene__title {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--color-text-primary);
  flex: 1;
}

.review-scene__tabs {
  display: inline-flex;
  gap: 0.25rem;
  padding: 0.25rem;
  border-radius: 0.625rem;
  background: var(--color-surface-sunken);
}

.review-scene__tab {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.375rem 0.75rem;
  border-radius: 0.5rem;
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  border: none;
  background: transparent;
  transition: background 0.2s ease;
}

.review-scene__tab.is-active {
  background: var(--color-surface-raised);
  color: var(--color-text-primary);
  font-weight: 500;
}

.review-scene__layout {
  display: grid;
  gap: 1rem;
}

@media (min-width: 768px) {
  .review-scene__layout {
    grid-template-columns: 1fr min(18rem, 34%);
    align-items: start;
  }
}

.review-scene__detail-date {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  margin-bottom: 0.5rem;
}

.review-scene__detail-summary {
  font-size: 0.9375rem;
  line-height: 1.6;
  color: var(--color-text-primary);
  margin-bottom: 0.625rem;
}

.review-scene__detail-chip {
  display: inline-block;
  font-size: 0.6875rem;
  padding: 0.125rem 0.5rem;
  border-radius: 999px;
  background: var(--color-surface-sunken);
  color: var(--color-text-secondary);
  margin-bottom: 1rem;
}

.review-scene__detail-actions {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.review-scene__multi-hint {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  margin-bottom: 0.5rem;
}

.review-scene__multi-item {
  display: block;
  width: 100%;
  text-align: left;
  padding: 0.5rem 0;
  border: none;
  border-bottom: 1px solid var(--color-border);
  background: none;
  font-size: 0.875rem;
  color: var(--color-text-primary);
  cursor: pointer;
}

.review-scene__delete-error {
  font-size: 0.8125rem;
  color: var(--color-danger);
  margin-bottom: 0.75rem;
}

.review-scene__delete-btn {
  color: var(--color-danger) !important;
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

.confirm-dialog__danger-btn {
  background: var(--color-danger) !important;
  color: #fff !important;
}

.review-scene__multi-item:last-child {
  border-bottom: none;
}
</style>
