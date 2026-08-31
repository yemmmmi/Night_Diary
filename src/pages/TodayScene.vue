<script setup lang="ts">
import { computed, nextTick, onActivated, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { PhCaretLeft, PhCaretRight, PhNotePencil, PhPlus } from '@phosphor-icons/vue'

import EmotionChips from '@/features/card/EmotionChips.vue'
import GameButton from '@/shared/components/GameButton.vue'
import InkCheck from '@/shared/components/InkCheck.vue'
import { usePlanStore } from '@/stores/plan'
import { useCardStore } from '@/stores/card'
import { listDiaryEntries, type DiaryEntry } from '@/shared/api/diary'
import { findCardForDiary } from '@/shared/utils/cardFormat'
import { diaryEntrySummary } from '@/shared/utils/diaryFormat'
import { parseLocalDate, toIsoDate } from '@/shared/utils/diaryFormat'
import { chineseDateLabel, todaySubtitle } from '@/shared/utils/todayFormat'
import { ledgerLine, recurrenceLabel, summarizePlanProgress, type PlanProgress } from '@/shared/utils/planProgress'
import type { PlanItem, TaskItem } from '@/shared/api/plan'

defineOptions({ name: 'TodayScene' })

const router = useRouter()
const planStore = usePlanStore()
const cardStore = useCardStore()

const anchorDate = ref(toIsoDate(new Date()))
const entries = ref<DiaryEntry[]>([])
const loadingEntries = ref(false)
const newTaskTitle = ref('')
const pullingPlanId = ref<string | null>(null)
const pullingTitle = ref('')
const completingTaskId = ref<string | null>(null)
const completingValue = ref('')
/** 翻页方向：prev 向右滑入、next 向左滑入（motion.css page-turn）。 */
const turnDir = ref<'prev' | 'next' | null>(null)

const turnClass = computed(() =>
  turnDir.value === 'prev' ? 'page-turn-right' : turnDir.value === 'next' ? 'page-turn-left' : '',
)

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

const planRows = computed(() => {
  const today = toIsoDate(new Date())
  return activePlans.value.map((p) => {
    const progress = summarizePlanProgress(p, today)
    return { plan: p, progress, stamp: recurrenceLabel(p.recurrence), ledger: ledgerLine(progress) }
  })
})

/** 进度条填充用 transform 缩放，避免触发布局重排。 */
function barStyle(p: PlanProgress): Record<string, string> {
  return { transform: `scaleX(${p.rate ?? 0})` }
}

function startPull(p: PlanItem) {
  pullingPlanId.value = p.id
  pullingTitle.value = p.title
}

async function submitPull() {
  const planId = pullingPlanId.value
  if (!planId) return
  const title = pullingTitle.value.trim()
  if (!title) return
  const ok = await planStore.pullToToday(planId, title)
  if (ok) cancelPull()
}

function cancelPull() {
  pullingPlanId.value = null
  pullingTitle.value = ''
}

function planOf(task: TaskItem): PlanItem | null {
  if (!task.plan_id) return null
  return planStore.plans.find((p) => p.id === task.plan_id) ?? null
}

function planHasTarget(p: PlanItem | null): boolean {
  return p != null && p.target_value != null && p.target_value > 0
}

/** 勾选：有目标的计划先记实际值；其余沿用原 toggle 路径（含取消勾选）。 */
async function onToggleTask(task: TaskItem) {
  if (task.status === 'done') {
    await planStore.toggleTask(task.id, task.status)
    return
  }
  if (planHasTarget(planOf(task))) {
    completingTaskId.value = task.id
    completingValue.value = ''
    return
  }
  await planStore.toggleTask(task.id, task.status)
}

async function confirmActual() {
  const taskId = completingTaskId.value
  if (!taskId) return
  const raw = completingValue.value.trim()
  const parsed = raw === '' ? Number.NaN : Number.parseFloat(raw)
  const actualValue = Number.isFinite(parsed) ? parsed : undefined
  cancelCompleting()
  await planStore.completeTask(taskId, actualValue)
}

async function skipActual() {
  const taskId = completingTaskId.value
  if (!taskId) return
  cancelCompleting()
  await planStore.completeTask(taskId)
}

function cancelCompleting() {
  completingTaskId.value = null
  completingValue.value = ''
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
  const dir: 'prev' | 'next' = delta < 0 ? 'prev' : 'next'
  turnDir.value = null
  const next = parseLocalDate(anchorDate.value)
  next.setDate(next.getDate() + delta)
  anchorDate.value = toIsoDate(next)
  await loadEntries()
  // 先清类再挂新类，保证连续点击时动画能重新触发。
  await nextTick()
  turnDir.value = dir
}

/** 翻页动画播完后清掉方向类，DOM 回到无动效基态。 */
function onTurnEnd(event: AnimationEvent) {
  if (event.animationName.startsWith('page-turn')) turnDir.value = null
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
    <div
      class="today-scene__main"
      :class="turnClass"
      data-testid="today-main"
      @animationend="onTurnEnd"
    >
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
            :class="{ 'is-done': t.status === 'done' }"
            data-testid="today-task-row"
          >
            <div class="today-task__check">
              <InkCheck :checked="t.status === 'done'" @toggle="onToggleTask(t)" />
              <span class="today-task__title ink-strike">
                {{ t.title }}
              </span>
            </div>
            <span v-if="planTitleOf(t)" class="today-task__origin">{{ planTitleOf(t) }}</span>
            <div
              v-if="completingTaskId === t.id"
              class="today-actual"
              data-testid="today-actual-form"
            >
              <input
                v-model="completingValue"
                type="text"
                inputmode="decimal"
                class="today-actual__input"
                data-testid="today-actual-input"
                aria-label="实际值（可选）"
                placeholder="实际值（可选）"
                maxlength="16"
                @keydown.enter.prevent="confirmActual"
                @keydown.esc.prevent="cancelCompleting"
              />
              <button
                type="button"
                class="today-actual__btn"
                data-testid="today-actual-confirm"
                @click="confirmActual"
              >
                确定
              </button>
              <button
                type="button"
                class="today-actual__btn"
                data-testid="today-actual-skip"
                @click="skipActual"
              >
                跳过
              </button>
            </div>
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
        <template v-if="planRows.length === 0">
          <p class="today-blank">还没有进行中的计划。</p>
        </template>
        <ul v-else class="today-plans">
          <li
            v-for="row in planRows"
            :key="row.plan.id"
            class="today-plan"
            data-testid="today-plan-row"
          >
            <div class="today-plan__head">
              <p class="today-plan__title">{{ row.plan.title }}</p>
              <span v-if="row.stamp" class="today-plan__stamp">{{ row.stamp }}</span>
            </div>
            <p class="today-plan__ledger" data-testid="today-plan-ledger">{{ row.ledger }}</p>
            <div
              v-if="row.progress.rate !== null"
              class="today-plan__bar"
              data-testid="today-plan-bar"
            >
              <div class="today-plan__bar-fill" :style="barStyle(row.progress)"></div>
            </div>
            <p v-if="row.plan.motivation" class="today-plan__motivation">{{ row.plan.motivation }}</p>
            <button
              type="button"
              class="today-plan__pull"
              data-testid="today-plan-pull"
              @click="startPull(row.plan)"
            >
              拉一条
            </button>
            <div v-if="pullingPlanId === row.plan.id" class="today-plan__pull-form">
              <input
                v-model="pullingTitle"
                type="text"
                class="today-plan__pull-input"
                data-testid="today-plan-pull-input"
                maxlength="200"
                @keydown.enter.prevent="submitPull"
                @keydown.esc.prevent="cancelPull"
              />
              <button
                type="button"
                class="today-plan__pull-submit"
                data-testid="today-plan-pull-submit"
                @click="submitPull"
              >
                添加
              </button>
            </div>
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
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
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
  min-width: 0;
}

/* 完成态：划线由全局 ink-strike 伪元素绘制，这里只做淡墨化 */
.today-task.is-done .today-task__title {
  color: var(--color-text-faint);
}

.today-task__origin {
  font-size: 0.6875rem;
  color: var(--color-text-faint);
  white-space: nowrap;
  flex-shrink: 0;
}

/* 勾选有目标计划的待办时，行内展开的实际值小输入 */
.today-actual {
  flex: 1 0 100%;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.25rem;
  padding-left: 1.875rem;
}

.today-actual__input {
  width: 4.5rem;
  flex-shrink: 0;
  border: none;
  border-bottom: 1px solid var(--color-line);
  background: transparent;
  color: var(--color-text-primary);
  font-family: var(--font-ui);
  font-size: 0.75rem;
  padding: 0.25rem 0.125rem;
  outline: none;
  font-variant-numeric: tabular-nums;
  transition: border-color var(--dur-fast) var(--ease-out-quart);
}

.today-actual__input:focus {
  border-bottom-color: var(--color-accent);
}

.today-actual__btn {
  flex-shrink: 0;
  padding: 0;
  border: none;
  background: transparent;
  font-family: var(--font-ui);
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: color var(--dur-fast) var(--ease-out-quart);
}

.today-actual__btn:hover {
  color: var(--color-text-primary);
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

.today-plan__head {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
}

.today-plan__title {
  margin: 0;
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-text-primary);
  min-width: 0;
}

/* 周期印章：灰墨底白字小字，与标题同行 */
.today-plan__stamp {
  flex-shrink: 0;
  padding: 0.0625rem 0.375rem;
  border-radius: 3px;
  background: var(--color-text-secondary);
  color: var(--color-bg);
  font-family: var(--font-ui);
  font-size: 0.625rem;
  letter-spacing: 0.08em;
  line-height: 1.5;
  white-space: nowrap;
}

/* 账簿一行三档数字：只陈述，不评判 */
.today-plan__ledger {
  margin: 0.25rem 0 0;
  font-size: 0.6875rem;
  line-height: 1.6;
  color: var(--color-text-secondary);
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.02em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.today-plan__bar {
  margin-top: 0.375rem;
  height: 2px;
  border-radius: 1px;
  background: var(--color-line);
  overflow: hidden;
}

.today-plan__bar-fill {
  height: 100%;
  background: var(--color-accent);
  transform-origin: left center;
  transition: transform var(--dur-fast) var(--ease-out-quart);
}

.today-plan__motivation {
  margin: 0.25rem 0 0;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  line-height: 1.6;
  border-left: 2px solid var(--color-accent);
  padding-left: 0.5rem;
}

/* 拉一条：淡墨下划线文字链 */
.today-plan__pull {
  margin: 0.4375rem 0 0;
  padding: 0;
  border: none;
  background: transparent;
  font-family: var(--font-ui);
  font-size: 0.6875rem;
  color: var(--color-text-faint);
  text-decoration: underline;
  text-underline-offset: 0.1875rem;
  cursor: pointer;
  transition: color var(--dur-fast) var(--ease-out-quart);
}

.today-plan__pull:hover {
  color: var(--color-text-secondary);
}

.today-plan__pull-form {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  margin-top: 0.375rem;
}

.today-plan__pull-input {
  flex: 1;
  min-width: 0;
  border: none;
  border-bottom: 1px solid var(--color-line);
  background: transparent;
  color: var(--color-text-primary);
  font-size: 0.75rem;
  padding: 0.25rem 0.125rem;
  outline: none;
  transition: border-color var(--dur-fast) var(--ease-out-quart);
}

.today-plan__pull-input:focus {
  border-bottom-color: var(--color-accent);
}

.today-plan__pull-submit {
  flex-shrink: 0;
  padding: 0;
  border: none;
  background: transparent;
  font-family: var(--font-ui);
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: color var(--dur-fast) var(--ease-out-quart);
}

.today-plan__pull-submit:hover {
  color: var(--color-text-primary);
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
