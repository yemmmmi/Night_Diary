<script setup lang="ts">
import { computed, onActivated, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { PhArrowSquareOut } from '@phosphor-icons/vue'

import AITypingIndicator from '@/shared/components/AITypingIndicator.vue'
import { weeklyCopy } from '@/shared/copy/weekly'
import { timelineCopy as copy } from '@/shared/copy/timeline'
import { useWeeklyStore } from '@/stores/weekly'
import { usePlanStore } from '@/stores/plan'
import {
  diarySummary,
  endOfWeekSunday,
  parseLocalDate,
  startOfWeekMonday,
  toIsoDate,
} from '@/shared/utils/diaryFormat'
import { chineseDateLabel } from '@/shared/utils/todayFormat'
import type { SourceRef, WeekTaskItem } from '@/shared/api/weekly'

const props = withDefaults(
  defineProps<{
    weekStartIso: string
    /** 洞悉页自管 weekly store（最近几封），传 false 关闭自动补拉。 */
    autoload?: boolean
  }>(),
  {
    autoload: true,
  },
)

const router = useRouter()
const weeklyStore = useWeeklyStore()
const planStore = usePlanStore()

const expanded = ref(false)

const currentWeekStartIso = computed(() => toIsoDate(startOfWeekMonday(new Date())))
const isCurrentWeek = computed(() => props.weekStartIso === currentWeekStartIso.value)

const report = computed(() =>
  weeklyStore.reports.find((r) => r.period_start === props.weekStartIso) ?? null,
)

const previewText = computed(() =>
  report.value ? diarySummary(report.value.content, 160) : '',
)

const hasStructuredPlan = computed(
  () =>
    report.value != null &&
    (report.value.plan_executions.length > 0 || report.value.week_tasks.length > 0),
)

const showGenerate = computed(() => isCurrentWeek.value && report.value == null)

/** 信笺抬头：衬线周期「八月二十四日 – 三十日」，同月省去后一个月名。 */
const periodLabel = computed(() => {
  const startIso = report.value?.period_start ?? props.weekStartIso
  const endIso =
    report.value?.period_end ?? toIsoDate(endOfWeekSunday(parseLocalDate(startIso)))
  const start = chineseDateLabel(startIso)
  const end = chineseDateLabel(endIso)
  if (!start || !end) return startIso
  if (start.slice(0, 2) === end.slice(0, 2)) return `${start} – ${end.slice(2)}`
  return `${start} – ${end}`
})

/** 记录页需要完整历史；洞悉页只装最近几封时（loadedLimit < 52）补拉回全量。 */
function needsFullHistory(): boolean {
  return weeklyStore.reports.length === 0 || (weeklyStore.loadedLimit ?? 52) < 52
}

function ensureLoaded() {
  if (!props.autoload || !needsFullHistory()) return
  weeklyStore.loadReports().catch(() => {})
}

onMounted(ensureLoaded)
onActivated(ensureLoaded)

function diaryRefs(items: SourceRef[]) {
  return items.filter((r) => r.type === 'diary')
}

function openRef(refId: string | number) {
  router.push(`/write/${refId}`)
}

async function onGenerate() {
  try {
    await weeklyStore.generate()
  } catch {
    /* surfaced via weeklyStore.error */
  }
}

async function onRegenerate() {
  try {
    await weeklyStore.regenerate()
  } catch {
    /* surfaced via weeklyStore.error */
  }
}

async function onToggleTask(task: WeekTaskItem) {
  const next = task.status === 'done' ? 'pending' : 'done'
  try {
    await planStore.toggleTask(task.task_id, task.status)
    task.status = next
  } catch {
    /* surfaced via planStore.error */
  }
}
</script>

<template>
  <article class="weekly-letter" data-testid="weekly-letter">
    <header class="weekly-letter__head">
      <div class="weekly-letter__head-text">
        <p class="weekly-letter__kicker">{{ weeklyCopy.letterTitle }}</p>
        <h2 class="weekly-letter__period">{{ periodLabel }}</h2>
      </div>
      <button
        v-if="showGenerate"
        type="button"
        class="weekly-letter__action"
        :disabled="weeklyStore.generating"
        @click="onGenerate"
      >
        {{ weeklyCopy.generate }}
      </button>
      <button
        v-else-if="isCurrentWeek && report"
        type="button"
        class="weekly-letter__action"
        :disabled="weeklyStore.generating"
        @click="onRegenerate"
      >
        {{ weeklyCopy.regenerate }}
      </button>
    </header>

    <p v-if="weeklyStore.error" class="weekly-letter__error">{{ weeklyStore.error }}</p>

    <div v-if="weeklyStore.generating" class="weekly-letter__typing">
      <AITypingIndicator :label="weeklyCopy.generating" />
    </div>

    <template v-else-if="report">
      <p class="weekly-letter__meta">
        {{ weeklyCopy.diaryCount(report.diary_count) }} · {{ weeklyCopy.cardCount(report.card_count) }}
      </p>
      <p class="weekly-letter__content font-diary">
        {{ expanded ? report.content : previewText }}
      </p>
      <button type="button" class="weekly-letter__toggle" @click="expanded = !expanded">
        {{ expanded ? weeklyCopy.collapse : weeklyCopy.expand }}
      </button>

      <div v-if="hasStructuredPlan" class="letter-plan">
        <p class="letter-plan__title">{{ copy.planSectionTitle }}</p>
        <div v-for="pe in report.plan_executions" :key="pe.plan_id" class="letter-plan__row">
          <span class="letter-plan__name">{{ pe.title }}</span>
          <span class="letter-plan__count">{{ pe.done }}/{{ pe.total }}</span>
          <button
            v-for="(r, i) in diaryRefs(pe.source_refs)"
            :key="i"
            type="button"
            class="letter-plan__ref"
            @click="openRef(r.id)"
          >
            {{ copy.fromDiary(r.date) }} <PhArrowSquareOut :size="12" />
          </button>
        </div>

        <label v-for="task in report.week_tasks" :key="task.task_id" class="letter-plan__task">
          <input
            type="checkbox"
            :checked="task.status === 'done'"
            @change="onToggleTask(task)"
          />
          <span class="letter-plan__task-title" :class="{ 'is-done': task.status === 'done' }">
            {{ task.title }}
          </span>
          <span v-if="task.source === 'agent'" class="letter-plan__task-source">
            {{ copy.aiSuggested }}
          </span>
        </label>
      </div>
    </template>

    <p v-else class="weekly-letter__empty">
      {{ isCurrentWeek ? weeklyCopy.emptyHint : copy.noLetterThisWeek }}
    </p>
  </article>
</template>

<style scoped>
/* 纸感信笺：diary-surface 纸面 + 细线边 + 文楷正文（规格 §5.4） */
.weekly-letter {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 1.25rem 1.5rem 1.375rem;
  background: var(--color-diary-surface);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-inner);
  box-shadow: var(--shadow-panel);
}

.weekly-letter__head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 0.75rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid var(--color-line);
}

.weekly-letter__kicker {
  margin: 0 0 0.25rem;
  font-size: 0.6875rem;
  letter-spacing: 0.24em;
  color: var(--color-text-faint);
}

.weekly-letter__period {
  margin: 0;
  font-family: var(--font-display);
  font-size: 1.0625rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--color-text-primary);
}

/* 生成 / 重新生成：淡墨下划线文字链 */
.weekly-letter__action {
  flex-shrink: 0;
  padding: 0.125rem 0;
  border: none;
  background: transparent;
  color: var(--color-accent);
  font-family: var(--font-ui);
  font-size: 0.75rem;
  text-decoration: underline;
  text-underline-offset: 0.25rem;
  cursor: pointer;
  transition: color var(--dur-fast) var(--ease-out-quart);
}

.weekly-letter__action:hover:not(:disabled) {
  color: var(--color-accent-muted);
}

.weekly-letter__action:disabled {
  opacity: 0.6;
  cursor: default;
}

.weekly-letter__error {
  font-size: 0.8125rem;
  color: var(--color-danger);
  margin: 0;
}

.weekly-letter__meta {
  font-size: 0.6875rem;
  color: var(--color-text-faint);
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.02em;
  margin: 0;
}

.weekly-letter__content {
  font-size: 0.9375rem;
  line-height: 2;
  color: var(--color-text-primary);
  margin: 0;
  white-space: pre-line;
}

.weekly-letter__toggle {
  align-self: flex-start;
  border: none;
  background: transparent;
  color: var(--color-text-faint);
  font-size: 0.75rem;
  text-decoration: underline;
  text-underline-offset: 0.1875rem;
  cursor: pointer;
  padding: 0;
  transition: color var(--dur-fast) var(--ease-out-quart);
}

.weekly-letter__toggle:hover {
  color: var(--color-text-secondary);
}

.weekly-letter__empty {
  font-size: 0.8125rem;
  color: var(--color-text-faint);
  margin: 0;
}

/* 信末计划执行：细线行 */
.letter-plan {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  border-top: 1px solid var(--color-line);
  padding-top: 0.75rem;
}

.letter-plan__title {
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.16em;
  color: var(--color-text-faint);
  margin: 0;
}

.letter-plan__row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8125rem;
}

.letter-plan__name {
  flex: 1;
  color: var(--color-text-primary);
}

.letter-plan__count {
  color: var(--color-text-secondary);
  font-variant-numeric: tabular-nums;
}

.letter-plan__ref {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  border: none;
  background: transparent;
  color: var(--color-accent);
  font-size: 0.75rem;
  cursor: pointer;
  padding: 0;
}

.letter-plan__task {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8125rem;
  cursor: pointer;
}

.letter-plan__task-title.is-done {
  text-decoration: line-through;
  color: var(--color-text-faint);
}

.letter-plan__task-source {
  font-size: 0.6875rem;
  color: var(--color-text-faint);
}
</style>
