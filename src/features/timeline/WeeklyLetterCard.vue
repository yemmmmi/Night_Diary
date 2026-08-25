<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { PhArrowSquareOut } from '@phosphor-icons/vue'

import AITypingIndicator from '@/shared/components/AITypingIndicator.vue'
import GameButton from '@/shared/components/GameButton.vue'
import GlassPanel from '@/shared/components/GlassPanel.vue'
import { weeklyCopy } from '@/shared/copy/weekly'
import { timelineCopy as copy } from '@/shared/copy/timeline'
import { useWeeklyStore } from '@/stores/weekly'
import { usePlanStore } from '@/stores/plan'
import { diarySummary, startOfWeekMonday, toIsoDate } from '@/shared/utils/diaryFormat'
import type { SourceRef, WeekTaskItem } from '@/shared/api/weekly'

const props = defineProps<{ weekStartIso: string }>()

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

onMounted(() => {
  if (weeklyStore.reports.length === 0) {
    weeklyStore.loadReports().catch(() => {})
  }
})

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
  <GlassPanel class="weekly-letter" elevated>
    <header class="weekly-letter__head">
      <h2 class="weekly-letter__title">{{ weeklyCopy.letterTitle }}</h2>
      <GameButton
        v-if="showGenerate"
        variant="primary"
        :disabled="weeklyStore.generating"
        @click="onGenerate"
      >
        {{ weeklyStore.generating ? weeklyCopy.generating : weeklyCopy.generate }}
      </GameButton>
      <GameButton
        v-else-if="isCurrentWeek && report"
        variant="secondary"
        :disabled="weeklyStore.generating"
        @click="onRegenerate"
      >
        {{ weeklyCopy.regenerate }}
      </GameButton>
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
  </GlassPanel>
</template>

<style scoped>
.weekly-letter {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.weekly-letter__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}
.weekly-letter__title {
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
}
.weekly-letter__error {
  font-size: 0.8125rem;
  color: var(--color-danger, #b3563e);
  margin: 0;
}
.weekly-letter__meta {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  margin: 0;
}
.weekly-letter__content {
  font-size: 0.875rem;
  line-height: 1.7;
  color: var(--color-text-primary);
  margin: 0;
  white-space: pre-line;
}
.weekly-letter__toggle {
  align-self: flex-start;
  border: none;
  background: transparent;
  color: var(--color-accent, #d4a574);
  font-size: 0.8125rem;
  cursor: pointer;
  padding: 0;
}
.weekly-letter__empty {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  margin: 0;
}
.letter-plan {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  border-top: 1px solid var(--color-border, rgba(61, 52, 41, 0.12));
  padding-top: 0.75rem;
}
.letter-plan__title {
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--color-text-secondary);
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
  color: var(--color-accent, #d4a574);
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
  color: var(--color-text-secondary);
}
.letter-plan__task-source {
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border, rgba(61, 52, 41, 0.12));
  border-radius: 999px;
  padding: 0.0625rem 0.5rem;
}
</style>
