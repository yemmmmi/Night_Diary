<script setup lang="ts">
import { computed, ref } from 'vue'
import { PhPlus } from '@phosphor-icons/vue'

import GameButton from '@/shared/components/GameButton.vue'
import InkCheck from '@/shared/components/InkCheck.vue'
import { usePlanStore } from '@/stores/plan'
import { toIsoDate } from '@/shared/utils/diaryFormat'
import { ledgerLine, recurrenceLabel, summarizePlanProgress, type PlanProgress } from '@/shared/utils/planProgress'
import type { PlanItem, TaskItem } from '@/shared/api/plan'

defineOptions({ name: 'TodayRail' })

const planStore = usePlanStore()

const newTaskTitle = ref('')
const pullingPlanId = ref<string | null>(null)
const pullingTitle = ref('')
const completingTaskId = ref<string | null>(null)
const completingValue = ref('')

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

async function addTodayTask() {
  const title = newTaskTitle.value.trim()
  if (!title) return
  const ok = await planStore.createTodayTask(title, toIsoDate(new Date()))
  if (ok) newTaskTitle.value = ''
}
</script>

<template>
  <aside class="today-rail">
    <section class="today-rail__block">
      <h2 class="today-rail__title">今日待办</h2>
      <template v-if="planStore.todayTasks.length === 0">
        <p class="today-rail__blank">今天还没有待办。</p>
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

    <section class="today-rail__block">
      <h2 class="today-rail__title">进行中的计划</h2>
      <template v-if="planRows.length === 0">
        <p class="today-rail__blank">还没有进行中的计划。</p>
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
</template>

<style scoped>
.today-rail {
  border-left: 1px solid var(--color-line);
  padding-left: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1.75rem;
  min-width: 0;
}

.today-rail__title {
  font-size: 0.8125rem;
  font-weight: 600;
  letter-spacing: 0.12em;
  color: var(--color-text-secondary);
  margin: 0 0 0.875rem;
}

.today-rail__blank {
  margin: 0;
  font-size: 0.8125rem;
  color: var(--color-text-faint);
}

.today-tasks {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}

.today-task {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.today-task__check {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
}

.today-task__title {
  font-size: 0.8125rem;
  line-height: 1.5;
  color: var(--color-text-primary);
}

.today-task.is-done .today-task__title {
  color: var(--color-text-faint);
}

.today-task__origin {
  font-size: 0.6875rem;
  color: var(--color-text-faint);
  padding-left: 1.625rem;
}

.today-actual {
  display: flex;
  gap: 0.375rem;
  padding-left: 1.625rem;
}

.today-actual__input {
  width: 6rem;
  padding: 0.25rem 0.375rem;
  border: 1px solid var(--color-line);
  border-radius: var(--radius-inner);
  background: transparent;
  font-size: 0.75rem;
  color: var(--color-text-primary);
  outline: none;
}

.today-actual__btn {
  border: 1px solid var(--color-line);
  background: transparent;
  border-radius: var(--radius-inner);
  padding: 0.25rem 0.5rem;
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
  cursor: pointer;
}

.today-actual__btn:hover {
  color: var(--color-text-primary);
}

.today-quick-add {
  display: flex;
  gap: 0.375rem;
  margin-top: 0.875rem;
}

.today-quick-input {
  flex: 1;
  min-width: 0;
  padding: 0.25rem 0;
  border: none;
  border-bottom: 1px solid var(--color-line);
  background: transparent;
  font-size: 0.8125rem;
  color: var(--color-text-primary);
  outline: none;
}

.today-quick-input::placeholder {
  color: var(--color-text-faint);
}

.today-quick-input:focus {
  border-bottom-color: var(--color-accent);
}

.today-plans {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.today-plan {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.today-plan__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem;
}

.today-plan__title {
  margin: 0;
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.today-plan__stamp {
  flex-shrink: 0;
  font-size: 0.625rem;
  color: var(--color-accent);
  border: 1px solid currentColor;
  border-radius: var(--radius-seal);
  padding: 0.0625rem 0.375rem;
}

.today-plan__ledger {
  margin: 0;
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
  font-variant-numeric: tabular-nums;
}

.today-plan__bar {
  height: 3px;
  background: var(--color-line);
  border-radius: 999px;
  overflow: hidden;
}

.today-plan__bar-fill {
  height: 100%;
  background: var(--color-accent);
  border-radius: inherit;
  transform-origin: left;
  transition: transform var(--dur-fast) var(--ease-out-quart);
}

.today-plan__motivation {
  margin: 0;
  font-size: 0.6875rem;
  color: var(--color-text-faint);
}

.today-plan__pull {
  align-self: flex-start;
  border: none;
  background: none;
  padding: 0;
  font-size: 0.6875rem;
  color: var(--color-accent);
  cursor: pointer;
}

.today-plan__pull:hover {
  text-decoration: underline;
}

.today-plan__pull-form {
  display: flex;
  gap: 0.375rem;
}

.today-plan__pull-input {
  flex: 1;
  min-width: 0;
  padding: 0.25rem 0.375rem;
  border: 1px solid var(--color-line);
  border-radius: var(--radius-inner);
  background: transparent;
  font-size: 0.75rem;
  color: var(--color-text-primary);
  outline: none;
}

.today-plan__pull-submit {
  border: 1px solid var(--color-line);
  background: transparent;
  border-radius: var(--radius-inner);
  padding: 0.25rem 0.5rem;
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
  cursor: pointer;
}

.today-plan__pull-submit:hover {
  color: var(--color-text-primary);
}
</style>
