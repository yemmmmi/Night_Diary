<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { PhPlay, PhStop, PhTimer } from '@phosphor-icons/vue'

import type { PlanItem } from '@/shared/api/plan'
import { checkinPlan } from '@/shared/api/plan'
import { planCopy } from '@/shared/copy/plan'
import { formatDuration } from '@/shared/utils/skillPlanProgress'

const props = defineProps<{
  plan: PlanItem
  /** 行级实时秒数（父层统一走表：快照秒数 + started_at 起的本地增量）。 */
  liveSeconds?: number
}>()

const emit = defineEmits<{
  refresh: []
}>()

const busy = ref(false)
const error = ref<string | null>(null)

/* ── checkin_total：每日打卡，点击进度 +1 ── */
const checkedInToday = computed(
  () => props.plan.today_progress?.today_checked_in ?? false,
)
const planCompleted = computed(() => props.plan.status === 'completed')

async function doCheckin() {
  if (busy.value || checkedInToday.value || planCompleted.value) return
  busy.value = true
  error.value = null
  try {
    await checkinPlan(props.plan.id, 'checkin')
    emit('refresh')
  } catch {
    error.value = planCopy.checkinFailed
  } finally {
    busy.value = false
  }
}

/* ── timer_daily：开始 / 停止计时（走表由父层统一驱动） ── */
const running = computed(() => props.plan.today_progress?.running ?? false)
const targetSeconds = computed(
  () => props.plan.today_progress?.target_seconds ?? (props.plan.target_value ?? 0) * 3600,
)
const seconds = computed(() => props.liveSeconds ?? props.plan.today_progress?.today_seconds ?? 0)
const streakDays = computed(() => props.plan.today_progress?.streak_days ?? 0)

/* 达标即弹窗（每个计划每天只弹一次；计时继续，由用户手动停止） */
const dailyDone = computed(
  () => targetSeconds.value > 0 && seconds.value >= targetSeconds.value,
)
const completionNoticeShownFor = ref<string | null>(null)
const showCompletion = ref(false)

watch(
  dailyDone,
  (done) => {
    if (!done) return
    const key = `${props.plan.id}:${props.plan.today_progress?.checkin_date ?? ''}`
    if (completionNoticeShownFor.value === key) return
    completionNoticeShownFor.value = key
    showCompletion.value = true
  },
  { immediate: true },
)

function dismissCompletion() {
  showCompletion.value = false
}

async function toggleTimer() {
  if (busy.value) return
  busy.value = true
  error.value = null
  try {
    await checkinPlan(props.plan.id, running.value ? 'stop' : 'start')
    emit('refresh')
  } catch {
    error.value = planCopy.timerFailed
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div v-if="plan.template === 'checkin_total' || plan.template === 'timer_daily'">
    <!-- 累计打卡：每日一次 -->
    <button
      v-if="plan.template === 'checkin_total'"
      type="button"
      class="skill-ctrl"
      :class="{ 'is-done': checkedInToday || planCompleted }"
      data-testid="checkin-btn"
      :disabled="busy || checkedInToday || planCompleted"
      @click.stop="doCheckin"
    >
      {{
        planCompleted
          ? planCopy.checkinPlanDone
          : checkedInToday
            ? planCopy.checkinTodayDone
            : planCopy.checkinAction
      }}
    </button>

    <!-- 每日计时：开始 / 停止 + 走表 -->
    <div v-else class="skill-ctrl-timer">
      <button
        type="button"
        class="skill-ctrl"
        :class="{ 'is-running': running }"
        data-testid="timer-btn"
        :disabled="busy"
        @click.stop="toggleTimer"
      >
        <PhPlay v-if="!running" :size="12" aria-hidden="true" />
        <PhStop v-else :size="12" aria-hidden="true" />
        {{ running ? planCopy.timerStop : planCopy.timerStart }}
      </button>
      <span
        v-if="running || dailyDone"
        class="skill-ctrl-timer__clock"
        :class="{ 'is-done': dailyDone }"
        data-testid="timer-elapsed"
      >
        <PhTimer :size="13" aria-hidden="true" />
        {{ formatDuration(seconds) }}{{ dailyDone ? ` · ${planCopy.timerDailyDone}` : '' }}
      </span>
      <span v-else-if="streakDays > 0" class="skill-ctrl-timer__streak">
        {{ planCopy.streakDays(streakDays) }}
      </span>
    </div>

    <p v-if="error" class="skill-ctrl__error" role="alert">{{ error }}</p>

    <!-- 达标弹窗：只提示，不自动停止计时 -->
    <div
      v-if="showCompletion"
      class="skill-ctrl-overlay"
      role="dialog"
      aria-modal="true"
      data-testid="timer-complete-dialog"
      @click.self="dismissCompletion"
    >
      <div class="skill-ctrl-dialog">
        <p class="skill-ctrl-dialog__title">{{ planCopy.timerCompleteTitle(plan.title) }}</p>
        <p class="skill-ctrl-dialog__desc">{{ planCopy.timerCompleteDesc }}</p>
        <button type="button" class="skill-ctrl-dialog__btn" @click="dismissCompletion">
          {{ planCopy.timerCompleteClose }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 打卡/计时按钮：细线小方钮，8px 圆角（区别于主按钮，行内轻量） */
.skill-ctrl {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.3125rem 0.875rem;
  border: 1px solid var(--color-line);
  border-radius: 8px;
  background: transparent;
  font-family: var(--font-ui);
  font-size: 0.8125rem;
  color: var(--color-text-primary);
  cursor: pointer;
  transition:
    border-color var(--motion-duration) var(--motion-ease),
    color var(--motion-duration) var(--motion-ease);
}

.skill-ctrl:hover:not(:disabled) {
  border-color: var(--color-accent);
  color: var(--color-accent);
}

.skill-ctrl.is-done {
  border-color: color-mix(in srgb, var(--color-accent) 40%, transparent);
  color: var(--color-accent);
  cursor: default;
}

.skill-ctrl.is-running {
  border-color: var(--color-accent);
  color: var(--color-accent);
}

.skill-ctrl:disabled {
  cursor: default;
}

.skill-ctrl:disabled:not(.is-done):not(.is-running) {
  opacity: 0.6;
}

.skill-ctrl-timer {
  display: inline-flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.skill-ctrl-timer__clock {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.8125rem;
  font-variant-numeric: tabular-nums;
  color: var(--color-text-secondary);
}

.skill-ctrl-timer__clock.is-done {
  color: var(--color-accent);
}

.skill-ctrl-timer__streak {
  font-size: 0.75rem;
  color: var(--color-text-faint);
}

.skill-ctrl__error {
  margin: 0.375rem 0 0;
  font-size: 0.75rem;
  color: var(--color-danger);
}

/* 达标弹窗：居中小对话框，遵循 MemoryScene 确认弹窗的墨色语言 */
.skill-ctrl-overlay {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1.5rem;
  background: color-mix(in srgb, var(--color-ink) 32%, transparent);
}

.skill-ctrl-dialog {
  max-width: 22rem;
  width: 100%;
  padding: 1.5rem 1.25rem;
  border-radius: 8px;
  background: var(--color-surface);
  border: 1px solid var(--color-line);
  text-align: center;
}

.skill-ctrl-dialog__title {
  margin: 0;
  font-family: var(--font-display);
  font-size: 1rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.skill-ctrl-dialog__desc {
  margin: 0.5rem 0 1rem;
  font-size: 0.8125rem;
  line-height: 1.7;
  color: var(--color-text-secondary);
}

.skill-ctrl-dialog__btn {
  padding: 0.4375rem 1.5rem;
  border: 1px solid var(--color-line);
  border-radius: 8px;
  background: transparent;
  font-family: var(--font-ui);
  font-size: 0.8125rem;
  color: var(--color-text-primary);
  cursor: pointer;
  transition:
    border-color var(--motion-duration) var(--motion-ease),
    color var(--motion-duration) var(--motion-ease);
}

.skill-ctrl-dialog__btn:hover {
  border-color: var(--color-accent);
  color: var(--color-accent);
}
</style>
