<script setup lang="ts">
import { computed, onActivated, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { PhCaretLeft, PhCaretRight, PhNotePencil, PhPlus } from '@phosphor-icons/vue'

import EmotionChips from '@/features/card/EmotionChips.vue'
import GameButton from '@/shared/components/GameButton.vue'
import { usePlanStore } from '@/stores/plan'
import { useCardStore } from '@/stores/card'
import { listDiaryEntries, type DiaryEntry } from '@/shared/api/diary'
import { findCardForDiary } from '@/shared/utils/cardFormat'
import { diaryEntrySummary } from '@/shared/utils/diaryFormat'
import { parseLocalDate, toIsoDate } from '@/shared/utils/diaryFormat'
import { chineseDateLabel, todaySubtitle } from '@/shared/utils/todayFormat'
import type { PlanItem, TaskItem } from '@/shared/api/plan'

defineOptions({ name: 'TodayScene' })

const router = useRouter()
const planStore = usePlanStore()
const cardStore = useCardStore()

const anchorDate = ref(toIsoDate(new Date()))
const entries = ref<DiaryEntry[]>([])
const loadingEntries = ref(false)
const newTaskTitle = ref('')

const bigDate = computed(() => chineseDateLabel(anchorDate.value))
const subtitle = computed(() => todaySubtitle(anchorDate.value))
const isToday = computed(() => anchorDate.value === toIsoDate(new Date()))

const activePlans = computed(() =>
  planStore.plans.filter((p) => p.status === 'active'),
)

function planTitleOf(task: TaskItem): string | null {
  if (!task.plan_id) return null
  const found = planStore.plans.find((p: PlanItem) => p.id === task.plan_id)
  return found ? found.title : null
}

async function loadEntries() {
  loadingEntries.value = true
  try {
    entries.value = await listDiaryEntries({
      date_from: anchorDate.value,
      date_to: anchorDate.value,
      limit: 100,
    })
  } catch {
    entries.value = []
  } finally {
    loadingEntries.value = false
  }
}

async function shiftDay(delta: number) {
  const next = parseLocalDate(anchorDate.value)
  next.setDate(next.getDate() + delta)
  anchorDate.value = toIsoDate(next)
  await loadEntries()
}

function goWrite() {
  router.push('/write')
}

async function addTodayTask() {
  const title = newTaskTitle.value.trim()
  if (!title) return
  const ok = await planStore.createTodayTask(title, toIsoDate(new Date()))
  if (ok) newTaskTitle.value = ''
}

function entryCard(entry: DiaryEntry) {
  return findCardForDiary(cardStore.cards, entry.id)
}

function entrySummary(entry: DiaryEntry): string {
  return diaryEntrySummary(entry, cardStore.cards, 160)
}

async function loadAll() {
  await Promise.all([
    loadEntries(),
    planStore.loadTodayTasks(),
    planStore.loadPlans(),
    cardStore.loadCards().catch(() => {}),
  ])
}

onMounted(loadAll)
onActivated(loadAll)
</script>

<template>
  <div class="today-scene">
    <div class="today-scene__main">
      <header class="today-head">
        <button
          type="button"
          class="today-head__nav"
          data-testid="today-prev"
          aria-label="前一天"
          @click="shiftDay(-1)"
        >
          <PhCaretLeft :size="16" />
        </button>
        <div class="today-head__center">
          <h1 class="today-head__date" data-testid="today-big-date">{{ bigDate }}</h1>
          <p class="today-head__sub">{{ subtitle }}</p>
        </div>
        <button
          type="button"
          class="today-head__nav"
          data-testid="today-next"
          aria-label="后一天"
          :disabled="isToday"
          @click="shiftDay(1)"
        >
          <PhCaretRight :size="16" />
        </button>
      </header>

      <section class="today-records">
        <h2 class="today-section-title">今日记录</h2>
        <template v-if="entries.length === 0">
          <p class="today-blank">这一页还是空白。</p>
          <GameButton variant="secondary" data-testid="today-write-cta" @click="goWrite">
            <PhNotePencil :size="14" />
            记一笔
          </GameButton>
        </template>
        <ul v-else class="today-records__list">
          <li v-for="e in entries" :key="e.id" class="today-record">
            <div class="today-record__meta">
              <EmotionChips
                v-if="entryCard(e)"
                :emotions="entryCard(e)!.emotions"
                :emotion="entryCard(e)!.emotion"
                :size="12"
              />
              <time class="today-record__time">{{ e.created_at.slice(11, 16) }}</time>
            </div>
            <p class="today-record__body font-diary">{{ entrySummary(e) }}</p>
          </li>
        </ul>
      </section>
    </div>

    <aside class="today-scene__rail">
      <section class="today-rail-block">
        <h2 class="today-section-title">今日待办</h2>
        <template v-if="planStore.todayTasks.length === 0">
          <p class="today-blank">今天还没有待办。</p>
        </template>
        <ul v-else class="today-tasks">
          <li
            v-for="t in planStore.todayTasks"
            :key="t.id"
            class="today-task"
            data-testid="today-task-row"
          >
            <label class="today-task__check">
              <input
                type="checkbox"
                :checked="t.status === 'done'"
                @change="planStore.toggleTask(t.id, t.status)"
              />
              <span class="today-task__title" :class="{ 'is-done': t.status === 'done' }">
                {{ t.title }}
              </span>
            </label>
            <span v-if="planTitleOf(t)" class="today-task__origin">{{ planTitleOf(t) }}</span>
          </li>
        </ul>
        <div class="today-quick-add">
          <input
            v-model="newTaskTitle"
            type="text"
            data-testid="today-add-input"
            class="today-quick-input"
            placeholder="记一条待办……"
            maxlength="200"
            @keydown.enter.prevent="addTodayTask"
          />
          <GameButton variant="ghost" data-testid="today-add-btn" @click="addTodayTask">
            <PhPlus :size="14" />
          </GameButton>
        </div>
      </section>

      <section class="today-rail-block">
        <h2 class="today-section-title">进行中的计划</h2>
        <template v-if="activePlans.length === 0">
          <p class="today-blank">还没有进行中的计划。</p>
        </template>
        <ul v-else class="today-plans">
          <li v-for="p in activePlans" :key="p.id" class="today-plan">
            <p class="today-plan__title">{{ p.title }}</p>
            <p v-if="p.motivation" class="today-plan__motivation">{{ p.motivation }}</p>
          </li>
        </ul>
      </section>
    </aside>
  </div>
</template>

<style scoped>
.today-scene {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 272px;
  gap: 0;
  max-width: 64rem;
  margin: 0 auto;
  padding: 1.75rem 1.5rem 2.5rem;
  color: var(--color-text-primary);
}

.today-scene__main {
  min-width: 0;
  padding-right: 1.75rem;
}

.today-scene__rail {
  border-left: 1px solid var(--color-line);
  padding-left: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1.75rem;
}

.today-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1.75rem;
}

.today-head__center {
  text-align: center;
}

.today-head__date {
  font-family: var(--font-display);
  font-size: 2.125rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  margin: 0;
  color: var(--color-text-primary);
}

.today-head__sub {
  margin: 0.25rem 0 0;
  font-size: 0.8125rem;
  color: var(--color-text-faint);
  letter-spacing: 0.06em;
}

.today-head__nav {
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

.today-head__nav:hover:not(:disabled) {
  color: var(--color-text-primary);
  background: var(--color-bg-elevated-2);
}

.today-head__nav:disabled {
  opacity: 0.35;
  cursor: default;
}

.today-section-title {
  font-family: var(--font-ui);
  font-size: 0.8125rem;
  font-weight: 600;
  letter-spacing: 0.12em;
  color: var(--color-text-secondary);
  margin: 0 0 0.875rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid var(--color-line);
}

.today-blank {
  margin: 0 0 0.875rem;
  font-size: 0.875rem;
  color: var(--color-text-faint);
}

.today-records__list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.today-record {
  padding: 0.875rem 0;
  border-bottom: 1px solid var(--color-line);
}

.today-record:last-child {
  border-bottom: none;
}

.today-record__meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.375rem;
}

.today-record__time {
  font-size: 0.75rem;
  color: var(--color-text-faint);
  font-variant-numeric: tabular-nums;
}

.today-record__body {
  margin: 0;
  font-size: 0.9375rem;
  line-height: 1.9;
  color: var(--color-text-primary);
}

.today-tasks,
.today-plans {
  list-style: none;
  margin: 0;
  padding: 0;
}

.today-task {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--color-line);
  font-size: 0.875rem;
}

.today-task:last-child {
  border-bottom: none;
}

.today-task__check {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  min-width: 0;
}

.today-task__title.is-done {
  text-decoration: line-through;
  color: var(--color-text-faint);
}

.today-task__origin {
  font-size: 0.6875rem;
  color: var(--color-text-faint);
  white-space: nowrap;
  flex-shrink: 0;
}

.today-quick-add {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  margin-top: 0.75rem;
}

.today-quick-input {
  flex: 1;
  min-width: 0;
  border: none;
  border-bottom: 1px solid var(--color-line);
  background: transparent;
  color: var(--color-text-primary);
  font-size: 0.875rem;
  padding: 0.375rem 0.125rem;
  outline: none;
  transition: border-color var(--dur-fast) var(--ease-out-quart);
}

.today-quick-input:focus {
  border-bottom-color: var(--color-accent);
}

.today-plan {
  padding: 0.625rem 0;
  border-bottom: 1px solid var(--color-line);
}

.today-plan:last-child {
  border-bottom: none;
}

.today-plan__title {
  margin: 0;
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.today-plan__motivation {
  margin: 0.25rem 0 0;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  line-height: 1.6;
  border-left: 2px solid var(--color-accent);
  padding-left: 0.5rem;
}

@media (max-width: 900px) {
  .today-scene {
    grid-template-columns: 1fr;
  }
  .today-scene__main {
    padding-right: 0;
    order: 3;
  }
  .today-scene__rail {
    border-left: none;
    padding-left: 0;
    order: 1;
    margin-bottom: 1.75rem;
  }
}
</style>
