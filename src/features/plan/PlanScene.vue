<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { PhArrowSquareOut, PhCaretRight, PhPlus } from '@phosphor-icons/vue'

import PlanCreateForm from '@/features/plan/PlanCreateForm.vue'
import PlanRefsBlock from '@/features/plan/PlanRefsBlock.vue'
import SkillPlanControls from '@/features/plan/SkillPlanControls.vue'
import GameButton from '@/shared/components/GameButton.vue'
import { planCopy } from '@/shared/copy/plan'
import { toIsoDate } from '@/shared/utils/diaryFormat'
import { ledgerLine, recurrenceLabel, summarizePlanProgress } from '@/shared/utils/planProgress'
import type { PlanProgress } from '@/shared/utils/planProgress'
import { skillPlanLine, skillPlanRate } from '@/shared/utils/skillPlanProgress'
import { openExternal } from '@/shared/utils/openExternal'
import { parseServerTime } from '@/shared/utils/timeFormat'
import { usePlanStore } from '@/stores/plan'
import type { PlanItem } from '@/shared/api/plan'

defineOptions({ name: 'PlanScene' })

const router = useRouter()
const planStore = usePlanStore()

const showCreateForm = ref(false)
const expandedPlanId = ref<string | null>(null)
const showArchived = ref(false)
/** 完成记实际值的行内输入（§6.3：有 target 的计划勾选完成时展开）。 */
const completing = ref<{ taskId: string; value: string } | null>(null)
/** 拉一条进今日待办的行内输入（预填计划标题，可改）。 */
const pulling = ref<{ planId: string; title: string } | null>(null)

const today = toIsoDate(new Date())

const activePlans = computed(() => planStore.plans.filter((p) => p.status === 'active'))
const archivedPlans = computed(() => planStore.plans.filter((p) => p.status !== 'active'))

function goToChat() {
  router.push('/chat')
}

function startManualCreate() {
  showCreateForm.value = true
}

function progressOf(plan: PlanItem): PlanProgress {
  return summarizePlanProgress(plan, today)
}

function stampOf(plan: PlanItem): string {
  return recurrenceLabel(plan.recurrence)
}

/* ── 模板计划（PR8 三模板）：账簿行/完成率切换 + 计时统一走表 ── */

const nowMs = ref(Date.now())
let ticker: ReturnType<typeof setInterval> | null = null
const hasRunningTimer = computed(() =>
  planStore.plans.some(
    (p) => p.template === 'timer_daily' && p.today_progress?.running,
  ),
)

watch(
  hasRunningTimer,
  (running) => {
    if (running && ticker == null) {
      ticker = setInterval(() => {
        nowMs.value = Date.now()
      }, 1000)
    } else if (!running && ticker != null) {
      clearInterval(ticker)
      ticker = null
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  if (ticker != null) clearInterval(ticker)
})

function isTemplatePlan(plan: PlanItem): boolean {
  return plan.template != null
}

function liveSecondsOf(plan: PlanItem): number {
  const snapshot = plan.today_progress
  if (!snapshot) return 0
  const base = snapshot.today_seconds ?? 0
  if (!snapshot.running || !snapshot.started_at) return base
  const start = parseServerTime(snapshot.started_at)
  if (Number.isNaN(start.getTime())) return base
  return base + Math.max(0, (nowMs.value - start.getTime()) / 1000)
}

function ledgerOf(plan: PlanItem): string {
  return plan.template
    ? skillPlanLine(plan, liveSecondsOf(plan))
    : ledgerLine(progressOf(plan))
}

function rateOf(plan: PlanItem): number | null {
  return plan.template
    ? skillPlanRate(plan, liveSecondsOf(plan))
    : progressOf(plan).rate
}

async function refreshPlans() {
  await planStore.loadPlans()
}

function openNodeLink(link: string) {
  openExternal(link)
}

function toggleExpand(planId: string) {
  expandedPlanId.value = expandedPlanId.value === planId ? null : planId
  completing.value = null
  pulling.value = null
}

function onToggleTask(plan: PlanItem, taskId: string, status: string) {
  if (status === 'done') {
    completing.value = null
    planStore.toggleTask(taskId, status)
    return
  }
  if (plan.target_value != null && plan.target_value > 0) {
    completing.value = { taskId, value: '' }
    return
  }
  planStore.completeTask(taskId)
}

async function confirmActual() {
  const state = completing.value
  if (!state) return
  const amount = Number.parseFloat(state.value)
  await planStore.completeTask(state.taskId, amount || undefined)
  completing.value = null
}

async function skipActual() {
  const state = completing.value
  if (!state) return
  completing.value = null
  await planStore.completeTask(state.taskId)
}

function startPull(plan: PlanItem) {
  pulling.value = { planId: plan.id, title: plan.title }
}

async function submitPull() {
  const state = pulling.value
  if (!state) return
  const title = state.title.trim()
  if (!title) return
  const ok = await planStore.pullToToday(state.planId, title)
  if (ok) pulling.value = null
}

onMounted(() => {
  planStore.loadPlans()
})
</script>

<template>
  <div class="plan-scene">
    <div class="plan-scene__head">
      <h2 class="plan-scene__title">{{ planCopy.title }}</h2>
      <GameButton variant="primary" data-testid="new-plan-btn" @click="startManualCreate">
        <PhPlus :size="14" />
        {{ planCopy.newPlan }}
      </GameButton>
    </div>

    <PlanCreateForm v-if="showCreateForm" class="plan-scene__form" @close="showCreateForm = false" />

    <section class="plan-scene__section">
      <div v-if="planStore.plans.length === 0" class="plan-scene__empty">
        <p class="plan-scene__empty-text">{{ planCopy.plansEmpty }}</p>
        <div class="plan-scene__empty-actions">
          <GameButton variant="primary" data-testid="plans-empty-manual" @click="startManualCreate">
            {{ planCopy.plansEmptyCta }}
          </GameButton>
          <GameButton variant="ghost" data-testid="plans-empty-ai" @click="goToChat">
            {{ planCopy.plansEmptyAiCta }}
          </GameButton>
        </div>
      </div>

      <template v-else>
        <ul class="plan-ledger-list">
          <li
            v-for="plan in activePlans"
            :key="plan.id"
            class="plan-row"
            data-testid="plan-row"
            @click="toggleExpand(plan.id)"
          >
            <div
              class="plan-row__head"
              role="button"
              tabindex="0"
              :title="planCopy.expandPlan"
              :aria-expanded="expandedPlanId === plan.id"
              @keydown.enter.prevent="toggleExpand(plan.id)"
            >
              <span class="plan-row__caret" :class="{ 'is-open': expandedPlanId === plan.id }" aria-hidden="true">
                <PhCaretRight :size="12" />
              </span>
              <span class="plan-row__title">{{ plan.title }}</span>
              <span v-if="stampOf(plan)" class="plan-stamp" data-testid="plan-stamp">{{ stampOf(plan) }}</span>
              <span v-if="plan.source === 'agent'" class="badge-agent">{{ planCopy.aiBadge }}</span>
            </div>
            <p class="plan-row__ledger" data-testid="plan-ledger">{{ ledgerOf(plan) }}</p>
            <div v-if="rateOf(plan) != null" class="plan-row__bar-track">
              <div
                class="plan-row__bar"
                data-testid="plan-progress-bar"
                :style="{ width: `${(rateOf(plan) ?? 0) * 100}%` }"
              />
            </div>
            <div
              v-if="plan.template === 'checkin_total' || plan.template === 'timer_daily'"
              class="plan-row__ctrl"
              @click.stop
            >
              <SkillPlanControls
                :plan="plan"
                :live-seconds="liveSecondsOf(plan)"
                @refresh="refreshPlans"
              />
            </div>

            <div v-if="expandedPlanId === plan.id" class="plan-row__detail" @click.stop>
              <p v-if="plan.motivation" class="plan-row__motivation">{{ plan.motivation }}</p>
              <PlanRefsBlock :refs="plan.source_refs" />
              <ul class="plan-row__tasks">
                <li v-for="task in plan.tasks" :key="task.id" class="plan-task">
                  <input
                    type="checkbox"
                    :checked="task.status === 'done'"
                    @change="onToggleTask(plan, task.id, task.status)"
                  />
                  <span class="plan-task__main">
                    <span class="plan-task__title" :class="{ 'is-done': task.status === 'done' }">
                      {{ task.title }}
                    </span>
                    <span
                      v-if="plan.template === 'milestones' && task.note"
                      class="plan-task__note"
                    >
                      {{ task.note }}
                    </span>
                  </span>
                  <button
                    v-if="task.link"
                    type="button"
                    class="plan-node__link"
                    data-testid="plan-node-link"
                    :title="task.link"
                    @click.stop="openNodeLink(task.link)"
                  >
                    <PhArrowSquareOut :size="11" aria-hidden="true" />
                    {{ planCopy.nodeReference }}
                  </button>
                  <template v-if="completing && completing.taskId === task.id">
                    <label class="task-actual">
                      <span class="task-actual__label">{{ planCopy.actualInputLabel }}</span>
                      <input
                        v-model="completing.value"
                        type="number"
                        min="0"
                        step="0.5"
                        data-testid="task-actual-input"
                        @keydown.enter.prevent="confirmActual"
                      />
                    </label>
                    <button
                      type="button"
                      class="plan-link-btn"
                      data-testid="task-actual-confirm"
                      @click="confirmActual"
                    >
                      {{ planCopy.actualConfirm }}
                    </button>
                    <button
                      type="button"
                      class="plan-link-btn plan-link-btn--muted"
                      data-testid="task-actual-skip"
                      @click="skipActual"
                    >
                      {{ planCopy.actualSkip }}
                    </button>
                  </template>
                </li>
              </ul>
              <div class="plan-row__actions">
                <button
                  v-if="!isTemplatePlan(plan) && (!pulling || pulling.planId !== plan.id)"
                  type="button"
                  class="plan-link-btn"
                  data-testid="plan-pull-link"
                  @click="startPull(plan)"
                >
                  {{ planCopy.pullToToday }}
                </button>
                <form v-if="pulling && pulling.planId === plan.id" class="plan-pull" @submit.prevent="submitPull">
                  <input
                    v-model="pulling.title"
                    type="text"
                    data-testid="plan-pull-input"
                    :placeholder="planCopy.pullPlaceholder"
                    maxlength="200"
                    @keydown.enter.prevent="submitPull"
                  />
                  <button type="submit" class="plan-link-btn" data-testid="plan-pull-submit">
                    {{ planCopy.pullSubmit }}
                  </button>
                </form>
                <button
                  type="button"
                  class="plan-link-btn plan-link-btn--danger"
                  @click="planStore.removePlan(plan.id)"
                >
                  {{ planCopy.delete }}
                </button>
              </div>
            </div>
          </li>
        </ul>

        <div v-if="archivedPlans.length > 0" class="plan-archived">
          <button
            type="button"
            class="plan-archived__toggle"
            data-testid="archived-toggle"
            :aria-expanded="showArchived"
            @click="showArchived = !showArchived"
          >
            <span class="plan-archived__caret" :class="{ 'is-open': showArchived }" aria-hidden="true">
              <PhCaretRight :size="12" />
            </span>
            {{ planCopy.archivedTitle }}（{{ archivedPlans.length }}）
          </button>
          <ul v-if="showArchived" class="plan-archived__list">
            <li v-for="plan in archivedPlans" :key="plan.id" class="plan-row plan-row--archived">
              <div class="plan-row__head">
                <span class="plan-row__title">{{ plan.title }}</span>
                <span v-if="stampOf(plan)" class="plan-stamp" data-testid="plan-stamp">{{ stampOf(plan) }}</span>
              </div>
              <p class="plan-row__ledger" data-testid="plan-ledger">{{ ledgerOf(plan) }}</p>
            </li>
          </ul>
        </div>
      </template>
    </section>
  </div>
</template>

<style scoped>
.plan-scene {
  padding: 1.25rem 1rem 1.5rem;
  max-width: 48rem;
  margin: 0 auto;
  color: var(--color-text-primary);
}

.plan-scene__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1.25rem;
}

.plan-scene__title {
  font-family: var(--font-display);
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
}

.plan-scene__form {
  margin-bottom: 1.5rem;
}

.plan-scene__section {
  margin-bottom: 2rem;
}

.plan-scene__empty {
  padding: 3rem 0 2rem;
  text-align: center;
}

.plan-scene__empty-text {
  margin: 0 0 0.375rem;
  font-family: var(--font-display);
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--color-text-primary);
  line-height: 1.6;
}

.plan-scene__empty-actions {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
  justify-content: center;
}

/* 账簿主体：细线行，无卡片无阴影 */
.plan-ledger-list {
  list-style: none;
  margin: 0;
  padding: 0;
  border-top: 1px solid var(--color-line);
}

.plan-row {
  padding: 0.875rem 0.25rem;
  border-bottom: 1px solid var(--color-line);
  cursor: pointer;
}

.plan-row__head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-width: 0;
}

.plan-row__caret {
  display: inline-flex;
  align-items: center;
  color: var(--color-text-faint);
  transition: transform var(--motion-duration) var(--motion-ease);
}

.plan-row__caret.is-open {
  transform: rotate(90deg);
}

.plan-row__title {
  font-family: var(--font-ui);
  font-weight: 600;
  font-size: 0.9375rem;
  color: var(--color-text-primary);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 周期印章：灰墨底白字、3px 圆角、字距加宽（视觉语言同 EmotionStamp，独立类） */
.plan-stamp {
  display: inline-block;
  padding: 0.125rem 0.5rem;
  border-radius: 3px;
  background: #8a7f6c;
  color: #fff;
  font-size: 0.6875rem;
  letter-spacing: 0.15em;
  white-space: nowrap;
}

.badge-agent {
  background: color-mix(in srgb, var(--color-accent) 15%, transparent);
  color: var(--color-accent);
  font-size: 0.6875rem;
  font-weight: 600;
  padding: 0.125rem 0.5rem;
  border-radius: 999px;
  white-space: nowrap;
}

.plan-row__ledger {
  margin: 0.375rem 0 0;
  padding-left: 1.25rem;
  font-family: var(--font-ui);
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  font-variant-numeric: tabular-nums;
}

.plan-row__bar-track {
  margin: 0.5rem 0 0 1.25rem;
  height: 2px;
  border-radius: 1px;
  background: var(--color-line);
  overflow: hidden;
}

.plan-row__bar {
  height: 2px;
  background: var(--color-accent);
}

/* 模板计划的打卡/计时控件行 */
.plan-row__ctrl {
  margin: 0.625rem 0 0 1.25rem;
}

.plan-task__main {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
  min-width: 0;
  flex: 1;
}

.plan-task__note {
  font-size: 0.75rem;
  line-height: 1.6;
  color: var(--color-text-secondary);
}

.plan-task__note.is-done {
  color: var(--color-text-faint);
}

/* milestones 节点参考链接：细线小签，外链图标 */
.plan-node__link {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.1875rem 0.5rem;
  border: 1px solid var(--color-line);
  border-radius: 999px;
  background: transparent;
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
  cursor: pointer;
  white-space: nowrap;
  transition:
    border-color var(--motion-duration) var(--motion-ease),
    color var(--motion-duration) var(--motion-ease);
}

.plan-node__link:hover {
  border-color: var(--color-accent);
  color: var(--color-accent);
}

.plan-row__detail {
  margin-top: 0.625rem;
  padding: 0.25rem 0 0.5rem 1.25rem;
  cursor: default;
}

.plan-row__motivation {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  margin: 0 0 0.5rem;
  line-height: 1.6;
}

.plan-row__tasks {
  list-style: none;
  margin: 0.5rem 0;
  padding: 0;
}

.plan-task {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
  padding: 0.375rem 0;
  border-bottom: 1px solid var(--color-line);
  font-size: 0.8125rem;
  color: var(--color-text-primary);
}

.plan-task__title.is-done {
  text-decoration: line-through;
  color: var(--color-text-faint);
}

.task-actual {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  margin-left: auto;
}

.task-actual__label {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

.task-actual input {
  width: 5rem;
  border: none;
  border-bottom: 1px solid var(--color-line);
  border-radius: 0;
  background: transparent;
  color: var(--color-text-primary);
  font-size: 0.8125rem;
  padding: 0.125rem 0.25rem;
  outline: none;
}

.task-actual input:focus {
  border-bottom-color: var(--color-accent);
}

.plan-row__actions {
  display: flex;
  align-items: center;
  gap: 1.25rem;
  margin-top: 0.625rem;
  flex-wrap: wrap;
}

.plan-link-btn {
  background: none;
  border: none;
  padding: 0;
  font-family: var(--font-ui);
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 3px;
}

.plan-link-btn:hover {
  color: var(--color-text-primary);
}

.plan-link-btn--muted {
  color: var(--color-text-faint);
}

.plan-link-btn--danger {
  color: var(--color-danger);
}

.plan-pull {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex: 1;
  min-width: 12rem;
}

.plan-pull input {
  flex: 1;
  max-width: 20rem;
  border: none;
  border-bottom: 1px solid var(--color-line);
  border-radius: 0;
  background: transparent;
  color: var(--color-text-primary);
  font-size: 0.8125rem;
  padding: 0.25rem 0.125rem;
  outline: none;
}

.plan-pull input:focus {
  border-bottom-color: var(--color-accent);
}

/* 已归档折叠区：底部收纳，淡墨呈现 */
.plan-archived {
  margin-top: 1.5rem;
}

.plan-archived__toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  background: none;
  border: none;
  padding: 0;
  font-family: var(--font-ui);
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  cursor: pointer;
}

.plan-archived__toggle:hover {
  color: var(--color-text-primary);
}

.plan-archived__caret {
  display: inline-flex;
  align-items: center;
  color: var(--color-text-faint);
  transition: transform var(--motion-duration) var(--motion-ease);
}

.plan-archived__caret.is-open {
  transform: rotate(90deg);
}

.plan-archived__list {
  list-style: none;
  margin: 0.5rem 0 0;
  padding: 0;
  border-top: 1px solid var(--color-line);
}

.plan-row--archived {
  cursor: default;
  padding: 0.625rem 0.25rem;
}

.plan-row--archived .plan-row__title {
  color: var(--color-text-faint);
  font-weight: 500;
}

.plan-row--archived .plan-row__ledger {
  color: var(--color-text-faint);
}
</style>
