<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PhArrowLeft, PhCalendarBlank, PhListBullets, PhCards, PhArrowSquareOut, PhMagnifyingGlass, PhXCircle } from '@phosphor-icons/vue'

import CalendarView from '@/features/review/CalendarView.vue'
import TimelineView from '@/features/review/TimelineView.vue'
import GameButton from '@/shared/components/GameButton.vue'
import GlassPanel from '@/shared/components/GlassPanel.vue'
import type { DiaryEntry } from '@/shared/api/diary'
import type { MemoryCard, CardSearchResult } from '@/shared/api/card'
import { searchCards, getMoodTrends } from '@/shared/api/card'
import type { MoodTrendPoint } from '@/shared/api/card'
import { useAnalysisStore } from '@/stores/analysis'
import { useDiaryStore } from '@/stores/diary'
import { useCardStore } from '@/stores/card'
import { formatApiError } from '@/shared/utils/apiError'
import { diaryStatus, diaryStatusLabel, diarySummary } from '@/shared/utils/diaryFormat'

type ReviewMode = 'calendar' | 'timeline' | 'cards'

const route = useRoute()
const router = useRouter()
const diaryStore = useDiaryStore()
const analysisStore = useAnalysisStore()
const cardStore = useCardStore()

const mode = ref<ReviewMode>('timeline')
const selectedDate = ref<string | null>(null)
const selectedEntry = ref<DiaryEntry | null>(null)
const showDeleteConfirm = ref(false)
const deleteError = ref<string | null>(null)

// ── Search state ──────────────────────────────────────────────────
const searchQuery = ref('')
const searchResults = ref<CardSearchResult[]>([])
const searchLoading = ref(false)
const searchActive = ref(false)

// ── Mood chart state ──────────────────────────────────────────────
const moodTrends = ref<MoodTrendPoint[]>([])
const chartEl = ref<HTMLDivElement | null>(null)
let chartInstance: any = null

const entriesOnSelectedDate = computed(() => {
  if (!selectedDate.value) return []
  return diaryStore.entries.filter((e) => e.date === selectedDate.value)
})

const routeDiaryId = computed(() => {
  const raw = route.params.diaryId
  const parsed = Number(raw)
  return Number.isFinite(parsed) ? parsed : null
})

const aiReplyPreview = computed(() => {
  const text =
    analysisStore.current?.ai_ans?.trim() || selectedEntry.value?.ai_ans?.trim() || ''
  return text ? diarySummary(text, 160) : null
})

const showAiPreview = computed(
  () =>
    selectedEntry.value != null &&
    diaryStatus(selectedEntry.value) !== 'draft' &&
    Boolean(aiReplyPreview.value),
)

function syncFromRoute() {
  if (!routeDiaryId.value) {
    selectedEntry.value = null
    analysisStore.clear()
    return
  }
  const found = diaryStore.entries.find((e) => e.id === routeDiaryId.value)
  if (found) {
    selectedEntry.value = found
    selectedDate.value = found.date
    void loadAnalysisForEntry(found)
  }
}

async function loadAnalysisForEntry(entry: DiaryEntry) {
  analysisStore.clear()
  if (diaryStatus(entry) === 'draft') return
  try {
    await analysisStore.loadForDiary(entry.id)
  } catch {
    // 无分析记录时静默
  }
}

function selectEntry(entry: DiaryEntry) {
  selectedEntry.value = entry
  selectedDate.value = entry.date
  void loadAnalysisForEntry(entry)
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
    void loadAnalysisForEntry(selectedEntry.value)
    router.replace({ name: 'review-detail', params: { diaryId: selectedEntry.value.id } })
  } else {
    analysisStore.clear()
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
    analysisStore.clear()
    await router.replace({ name: 'review' })
  } catch (err) {
    deleteError.value = formatApiError(err, '删除日记失败')
  }
}

function goHome() {
  router.push('/')
}

async function expandCard(card: MemoryCard) {
  try {
    const result = await cardStore.expandCard(card.card_id)
    await diaryStore.loadEntries()
    router.push(`/write/${result.diary_id}`)
  } catch (err) {
    deleteError.value = formatApiError(err, '展开卡片失败')
  }
}

async function deleteCard(card: MemoryCard) {
  try {
    await cardStore.removeCard(card.card_id)
    // Also remove from search results if active
    if (searchActive.value) {
      searchResults.value = searchResults.value.filter(r => r.card_id !== card.card_id)
    }
  } catch (err) {
    deleteError.value = formatApiError(err, '删除卡片失败')
  }
}

// ── Search ────────────────────────────────────────────────────────

async function doSearch() {
  const q = searchQuery.value.trim()
  if (!q) {
    searchActive.value = false
    searchResults.value = []
    return
  }
  searchLoading.value = true
  searchActive.value = true
  try {
    const result = await searchCards(q, 20)
    searchResults.value = result.results
  } catch (err) {
    deleteError.value = formatApiError(err, '搜索失败')
  } finally {
    searchLoading.value = false
  }
}

function clearSearch() {
  searchQuery.value = ''
  searchActive.value = false
  searchResults.value = []
}

// ── Mood chart ────────────────────────────────────────────────────

async function loadMoodTrends() {
  if (cardStore.cards.length < 2) return
  try {
    moodTrends.value = await getMoodTrends(30)
    await nextTick()
    renderMoodChart()
  } catch {
    moodTrends.value = []
  }
}

function renderMoodChart() {
  if (!chartEl.value || moodTrends.value.length < 2) return
  const echarts = (window as any).echarts
  if (!echarts) return

  const style = getComputedStyle(document.documentElement)
  const accent = style.getPropertyValue('--color-accent').trim() || '#D4A574'
  const muted = style.getPropertyValue('--color-text-secondary').trim() || '#7A6F63'
  const rule = style.getPropertyValue('--color-border').trim() || 'rgba(61,52,41,0.12)'
  const bg2 = style.getPropertyValue('--color-bg-elevated').trim() || '#F5F0E8'

  if (chartInstance) chartInstance.dispose()

  chartInstance = echarts.init(chartEl.value, null, { renderer: 'svg' })
  chartInstance.setOption({
    animation: false,
    grid: { top: 10, right: 24, bottom: 24, left: 40 },
    xAxis: {
      type: 'category',
      data: moodTrends.value.map(p => p.date.slice(5)),
      axisLine: { lineStyle: { color: rule } },
      axisLabel: { color: muted, fontSize: 10 },
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 1,
      interval: 0.25,
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: rule } },
      axisLabel: {
        color: muted, fontSize: 10,
        formatter: (v: number) => v === 0 ? '低' : v === 1 ? '高' : '',
      },
    },
    series: [{
      type: 'line',
      data: moodTrends.value.map(p => p.avg_mood),
      smooth: true,
      symbol: 'circle',
      symbolSize: 4,
      lineStyle: { color: accent, width: 2 },
      itemStyle: { color: accent },
      areaStyle: {
        color: {
          type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: accent + '33' },
            { offset: 1, color: accent + '00' },
          ],
        },
      },
    }],
    tooltip: {
      trigger: 'axis',
      appendToBody: true,
      formatter: (params: any) => {
        const p = params[0]
        return `${p.axisValue}<br/>平均心情: ${(p.value * 100).toFixed(0)}%`
      },
    },
  })

  window.addEventListener('resize', () => chartInstance?.resize())
}

function disposeChart() {
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
}

// Watch for mode changes to load chart
watch(
  () => mode.value,
  (val) => {
    if (val === 'cards') {
      nextTick(() => loadMoodTrends())
    } else {
      disposeChart()
    }
  },
)

onMounted(async () => {
  await Promise.all([diaryStore.loadEntries(), cardStore.loadCards()])
  syncFromRoute()
  if (mode.value === 'cards') {
    await nextTick()
    loadMoodTrends()
  }
})

onUnmounted(() => {
  disposeChart()
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
        <button
          type="button"
          class="review-scene__tab"
          :class="{ 'is-active': mode === 'cards' }"
          @click="mode = 'cards'"
        >
          <PhCards :size="16" />
          卡片
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
          v-else-if="mode === 'timeline'"
          :entries="diaryStore.entries"
          :selected-id="selectedEntry?.id ?? null"
          @select="selectEntry"
        />

        <!-- Cards grid -->
        <div v-else-if="mode === 'cards'" class="review-cards">
          <!-- Search bar -->
          <div class="review-cards__search">
            <div class="review-cards__search-row">
              <PhMagnifyingGlass :size="16" class="review-cards__search-icon" />
              <input
                v-model="searchQuery"
                class="review-cards__search-input"
                placeholder="搜索记忆卡片……"
                @keydown.enter="doSearch"
              />
              <button
                v-if="searchQuery"
                class="review-cards__search-clear"
                @click="clearSearch"
              >
                <PhXCircle :size="14" />
              </button>
            </div>
            <GameButton
              variant="ghost"
              :disabled="!searchQuery.trim() || searchLoading"
              @click="doSearch"
            >
              {{ searchLoading ? '搜索中……' : '搜索' }}
            </GameButton>
          </div>

          <!-- Mood trend chart -->
          <div v-if="moodTrends.length >= 2 && !searchActive" class="review-cards__chart">
            <p class="review-cards__chart-title">近 30 天情绪趋势</p>
            <div ref="chartEl" class="review-cards__chart-container" />
          </div>

          <!-- Search results -->
          <template v-if="searchActive">
            <p v-if="!searchLoading && searchResults.length === 0" class="review-cards__empty">
              没有找到匹配的记忆卡片
            </p>
            <div
              v-for="card in searchResults"
              :key="card.card_id"
              class="review-card-item glass-panel"
            >
              <div class="review-card-item__head">
                <span class="review-card-item__emotion">{{ card.emotion }}</span>
                <span class="review-card-item__type">
                  {{ card.card_type === 'quick' ? '极速' : card.card_type === 'guided' ? '引导' : '标准' }}
                </span>
              </div>
              <p v-if="card.event_summary" class="review-card-item__summary font-diary">
                {{ card.event_summary }}
              </p>
              <div v-if="card.tags.length > 0" class="review-card-item__tags">
                <span v-for="tag in card.tags" :key="tag" class="review-card-item__tag">{{ tag }}</span>
              </div>
              <div class="review-card-item__footer">
                <span class="review-card-item__time">
                  {{ new Date(card.created_at).toLocaleDateString('zh-CN') }}
                  {{ new Date(card.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }}
                </span>
                <div class="review-card-item__actions">
                  <button
                    v-if="!card.diary_id"
                    class="review-card-item__action-btn"
                    title="展开为日记"
                    @click="expandCard(card)"
                  >
                    <PhArrowSquareOut :size="14" />
                  </button>
                  <button
                    class="review-card-item__action-btn review-card-item__action-btn--danger"
                    title="删除"
                    @click="deleteCard(card)"
                  >&times;</button>
                </div>
              </div>
            </div>
          </template>

          <!-- Normal card list -->
          <template v-else>
            <div v-if="cardStore.cards.length === 0" class="review-cards__empty">
              <p>还没有记忆卡片</p>
              <p class="review-cards__empty-hint">在首页点击「记一笔」创建你的第一张卡片</p>
            </div>

          <div v-for="card in cardStore.cards" :key="card.card_id" class="review-card-item glass-panel">
            <div class="review-card-item__head">
              <span class="review-card-item__emotion">{{ card.emotion }}</span>
              <span class="review-card-item__type">
                {{ card.card_type === 'quick' ? '极速' : card.card_type === 'guided' ? '引导' : '标准' }}
              </span>
            </div>
            <p v-if="card.event_summary" class="review-card-item__summary font-diary">
              {{ card.event_summary }}
            </p>
            <div v-if="card.tags.length > 0" class="review-card-item__tags">
              <span
                v-for="tag in card.tags"
                :key="tag"
                class="review-card-item__tag"
              >
                {{ tag }}
              </span>
            </div>
            <div class="review-card-item__footer">
              <span class="review-card-item__time">
                {{ new Date(card.created_at).toLocaleDateString('zh-CN') }}
                {{ new Date(card.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }}
              </span>
              <div class="review-card-item__actions">
                <button
                  v-if="!card.diary_id"
                  class="review-card-item__action-btn"
                  title="展开为日记"
                  @click="expandCard(card)"
                >
                  <PhArrowSquareOut :size="14" />
                </button>
                <button
                  class="review-card-item__action-btn review-card-item__action-btn--danger"
                  title="删除"
                  @click="deleteCard(card)"
                >
                  &times;
                </button>
              </div>
            </div>
          </div>
        </template>
      </div>
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
          <div v-if="showAiPreview" class="review-scene__ai-block">
            <p class="review-scene__ai-label">AI 回信</p>
            <p class="review-scene__ai-preview font-diary">{{ aiReplyPreview }}</p>
          </div>
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

.review-scene__ai-block {
  margin-bottom: 1rem;
  padding: 0.75rem;
  border-radius: 0.625rem;
  border-left: 3px solid var(--color-accent);
  background: var(--color-surface-sunken);
}

.review-scene__ai-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-text-secondary);
  margin-bottom: 0.375rem;
}

.review-scene__ai-preview {
  font-size: 0.875rem;
  line-height: 1.65;
  color: var(--color-text-primary);
  white-space: pre-wrap;
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

/* ── Cards view ──────────────────────────────────────────────── */
.review-cards {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.review-cards__empty {
  text-align: center;
  padding: 3rem 1rem;
  color: var(--color-text-secondary);
  font-family: var(--font-ui);
  font-size: 0.9375rem;
}

.review-cards__empty-hint {
  font-size: 0.8125rem;
  margin-top: 0.5rem;
  opacity: 0.7;
}

/* ── Search bar ─────────────────────────────────────────────── */
.review-cards__search {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}

.review-cards__search-row {
  flex: 1;
  display: flex;
  align-items: center;
  padding: 0.5rem 0.75rem;
  border-radius: var(--radius-button, 0.75rem);
  border: 1px solid var(--color-border);
  background: var(--color-bg);
  transition: border-color var(--motion-duration, 220ms);
}

.review-cards__search-row:focus-within {
  border-color: var(--color-accent);
}

.review-cards__search-icon {
  color: var(--color-text-secondary);
  flex-shrink: 0;
}

.review-cards__search-input {
  flex: 1;
  border: none;
  background: none;
  outline: none;
  font-family: var(--font-ui);
  font-size: 0.8125rem;
  color: var(--color-text-primary);
  padding: 0 0.5rem;
}

.review-cards__search-input::placeholder {
  color: var(--color-text-secondary);
  opacity: 0.6;
}

.review-cards__search-clear {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  color: var(--color-text-secondary);
  cursor: pointer;
  padding: 0;
  flex-shrink: 0;
}

.review-cards__search-clear:hover {
  color: var(--color-danger);
}

/* ── Mood chart ─────────────────────────────────────────────── */
.review-cards__chart {
  margin-bottom: 1rem;
  padding: 0.75rem;
  border-radius: var(--radius-outer, 1rem);
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
}

.review-cards__chart-title {
  font-family: var(--font-ui);
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-text-secondary);
  margin-bottom: 0.375rem;
}

.review-cards__chart-container {
  width: 100%;
  height: 180px;
}

.review-card-item {
  padding: 1rem;
  border-radius: var(--radius-outer, 1rem);
}

.review-card-item__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.5rem;
}

.review-card-item__emotion {
  font-family: var(--font-ui);
  font-size: 0.9375rem;
  font-weight: 700;
  color: var(--color-accent);
}

.review-card-item__type {
  font-family: var(--font-ui);
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
  padding: 0.125rem 0.5rem;
  background: var(--color-bg-elevated-2);
  border-radius: 0.375rem;
}

.review-card-item__summary {
  font-size: 0.9375rem;
  color: var(--color-text-primary);
  line-height: 1.7;
  margin-bottom: 0.5rem;
}

.review-card-item__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  margin-bottom: 0.5rem;
}

.review-card-item__tag {
  font-family: var(--font-ui);
  font-size: 0.6875rem;
  color: var(--color-accent-muted);
  background: color-mix(in srgb, var(--color-accent) 10%, transparent);
  padding: 0.125rem 0.5rem;
  border-radius: 0.5rem;
}

.review-card-item__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.review-card-item__time {
  font-family: var(--font-ui);
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
}

.review-card-item__actions {
  display: flex;
  gap: 0.25rem;
}

.review-card-item__action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.625rem;
  height: 1.625rem;
  border-radius: 50%;
  border: 1px solid var(--color-border);
  background: none;
  color: var(--color-accent);
  cursor: pointer;
  font-size: 0.875rem;
  transition: all var(--motion-duration, 220ms);
}

.review-card-item__action-btn:hover {
  background: color-mix(in srgb, var(--color-accent) 12%, transparent);
}

.review-card-item__action-btn--danger {
  color: var(--color-text-secondary);
}

.review-card-item__action-btn--danger:hover {
  color: var(--color-danger);
  background: color-mix(in srgb, var(--color-danger) 10%, transparent);
}
</style>
