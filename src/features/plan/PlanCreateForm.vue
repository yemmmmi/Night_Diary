<script setup lang="ts">
import { reactive, ref } from 'vue'
import { PhPlus, PhX } from '@phosphor-icons/vue'

import GameButton from '@/shared/components/GameButton.vue'
import GlassPanel from '@/shared/components/GlassPanel.vue'
import { planCopy } from '@/shared/copy/plan'
import { usePlanStore } from '@/stores/plan'

defineOptions({ name: 'PlanCreateForm' })

const emit = defineEmits<{ close: [] }>()

const planStore = usePlanStore()

const form = reactive({
  title: '',
  motivation: '',
  tasks: [] as Array<{ title: string; due_date: string }>,
})
const submitting = ref(false)
const titleError = ref(false)

/** 周期三选项：无 / 每日 / 每周（每周时用周几 chip 多选，生成 weekly:2,4 串）。 */
const recurrenceMode = ref<'none' | 'daily' | 'weekly'>('none')
const weekdays = ref<number[]>([])
const WEEKDAY_OPTIONS = [1, 2, 3, 4, 5, 6, 7] as const
const WEEKDAY_LABELS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'] as const

/** 目标值一行三输入：数值 / 单位 / 周期。 */
const targetValueInput = ref('')
const targetUnitInput = ref('')
const targetPeriodInput = ref<'daily' | 'weekly' | 'total'>('weekly')

function toggleWeekday(day: number) {
  const index = weekdays.value.indexOf(day)
  if (index >= 0) weekdays.value.splice(index, 1)
  else weekdays.value.push(day)
}

function buildRecurrence(): string {
  if (recurrenceMode.value === 'daily') return 'daily'
  if (recurrenceMode.value === 'weekly' && weekdays.value.length > 0) {
    const days = [...weekdays.value].sort((a, b) => a - b)
    return `weekly:${days.join(',')}`
  }
  return 'none'
}

interface TargetPayload {
  target_value: number
  target_unit?: string
  target_period: 'daily' | 'weekly' | 'total'
}

/** 数值有效（正数）才组装目标字段，否则整个目标缺省。 */
function buildTarget(): TargetPayload | undefined {
  const value = Number.parseFloat(targetValueInput.value)
  if (!Number.isFinite(value) || value <= 0) return undefined
  return {
    target_value: value,
    target_unit: targetUnitInput.value.trim() || undefined,
    target_period: targetPeriodInput.value,
  }
}

function addTask() {
  form.tasks.push({ title: '', due_date: '' })
}

function removeTask(index: number) {
  form.tasks.splice(index, 1)
}

function cancel() {
  emit('close')
}

async function submit() {
  const title = form.title.trim()
  if (!title) {
    titleError.value = true
    return
  }
  titleError.value = false
  submitting.value = true
  const tasks = form.tasks
    .map((t) => ({ title: t.title.trim(), due_date: t.due_date || undefined }))
    .filter((t) => t.title)
  const ok = await planStore.createPlan({
    title,
    motivation: form.motivation.trim() || undefined,
    tasks: tasks.length > 0 ? tasks : undefined,
    recurrence: buildRecurrence(),
    ...buildTarget(),
  })
  submitting.value = false
  if (ok) emit('close')
}
</script>

<template>
  <GlassPanel class="plan-create-form" padding>
    <div class="plan-create-form__head">
      <h3 class="plan-create-form__title">{{ planCopy.newPlan }}</h3>
      <button type="button" class="plan-create-form__close" @click="cancel">
        <PhX :size="16" />
      </button>
    </div>

    <label class="plan-create-form__field">
      <span class="plan-create-form__label">{{ planCopy.formTitleLabel }}</span>
      <input
        v-model="form.title"
        type="text"
        data-testid="plan-title-input"
        class="plan-create-form__input"
        :class="{ 'is-error': titleError }"
        :placeholder="planCopy.formTitlePlaceholder"
        maxlength="200"
        @input="titleError = false"
      />
    </label>

    <label class="plan-create-form__field">
      <span class="plan-create-form__label">{{ planCopy.formMotivationLabel }}</span>
      <input
        v-model="form.motivation"
        type="text"
        data-testid="plan-motivation-input"
        class="plan-create-form__input"
        :placeholder="planCopy.formMotivationPlaceholder"
      />
    </label>

    <div class="plan-create-form__field">
      <span class="plan-create-form__label">{{ planCopy.recurrenceLabel }}</span>
      <div class="plan-create-form__seg" role="group">
        <button
          type="button"
          class="seg-btn"
          :class="{ 'is-active': recurrenceMode === 'none' }"
          data-testid="recurrence-none"
          @click="recurrenceMode = 'none'"
        >
          {{ planCopy.recurrenceNone }}
        </button>
        <button
          type="button"
          class="seg-btn"
          :class="{ 'is-active': recurrenceMode === 'daily' }"
          data-testid="recurrence-daily"
          @click="recurrenceMode = 'daily'"
        >
          {{ planCopy.recurrenceDaily }}
        </button>
        <button
          type="button"
          class="seg-btn"
          :class="{ 'is-active': recurrenceMode === 'weekly' }"
          data-testid="recurrence-weekly"
          @click="recurrenceMode = 'weekly'"
        >
          {{ planCopy.recurrenceWeekly }}
        </button>
      </div>
      <div v-if="recurrenceMode === 'weekly'" class="plan-create-form__weekdays">
        <span class="plan-create-form__weekday-label">{{ planCopy.recurrenceWeekdays }}</span>
        <button
          v-for="day in WEEKDAY_OPTIONS"
          :key="day"
          type="button"
          class="weekday-chip"
          :class="{ 'is-active': weekdays.includes(day) }"
          :data-testid="`weekday-chip-${day}`"
          @click="toggleWeekday(day)"
        >
          {{ WEEKDAY_LABELS[day - 1] }}
        </button>
      </div>
    </div>

    <div class="plan-create-form__field">
      <span class="plan-create-form__label">{{ planCopy.targetValueLabel }}</span>
      <div class="plan-create-form__target-row">
        <input
          v-model="targetValueInput"
          type="number"
          min="0"
          step="0.5"
          data-testid="target-value-input"
          class="plan-create-form__input plan-create-form__target-value"
          placeholder="4"
        />
        <input
          v-model="targetUnitInput"
          type="text"
          data-testid="target-unit-input"
          class="plan-create-form__input plan-create-form__target-unit"
          :placeholder="planCopy.targetUnitPlaceholder"
          maxlength="16"
        />
        <select
          v-model="targetPeriodInput"
          data-testid="target-period-select"
          class="plan-create-form__input plan-create-form__target-period"
        >
          <option value="daily">{{ planCopy.targetPeriodDaily }}</option>
          <option value="weekly">{{ planCopy.targetPeriodWeekly }}</option>
          <option value="total">{{ planCopy.targetPeriodTotal }}</option>
        </select>
      </div>
    </div>

    <div class="plan-create-form__field">
      <span class="plan-create-form__label">{{ planCopy.formTasksLabel }}</span>
      <div
        v-for="(task, index) in form.tasks"
        :key="index"
        class="plan-create-form__task-row"
      >
        <input
          v-model="task.title"
          type="text"
          data-testid="task-title-input"
          class="plan-create-form__input plan-create-form__task-title"
          :placeholder="planCopy.formTaskPlaceholder"
          maxlength="200"
        />
        <input
          v-model="task.due_date"
          type="date"
          class="plan-create-form__input plan-create-form__task-due"
          :aria-label="planCopy.formTaskDueLabel"
        />
        <button
          type="button"
          class="plan-create-form__remove"
          :title="planCopy.formRemoveTask"
          @click="removeTask(index)"
        >
          <PhX :size="14" />
        </button>
      </div>
      <button type="button" class="plan-create-form__add-task" data-testid="form-add-task" @click="addTask">
        <PhPlus :size="14" />
        {{ planCopy.formAddTask }}
      </button>
    </div>

    <div class="plan-create-form__actions">
      <GameButton variant="ghost" :disabled="submitting" @click="cancel">
        {{ planCopy.formCancel }}
      </GameButton>
      <GameButton variant="primary" :disabled="submitting" data-testid="plan-submit" @click="submit">
        {{ planCopy.formSubmit }}
      </GameButton>
    </div>
  </GlassPanel>
</template>

<style scoped>
.plan-create-form {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.plan-create-form__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.plan-create-form__title {
  margin: 0;
  font-family: var(--font-ui);
  font-size: 1rem;
  font-weight: 700;
  color: var(--color-text-primary);
}
.plan-create-form__close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  padding: 0.25rem;
  border-radius: 0.375rem;
}
.plan-create-form__close:hover {
  color: var(--color-text-primary);
  background: var(--color-bg-elevated-2);
}
.plan-create-form__field {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
.plan-create-form__label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-text-secondary);
}
.plan-create-form__input {
  border: 1px solid var(--color-border);
  border-radius: 0.5rem;
  background: var(--color-bg);
  color: var(--color-text-primary);
  font-size: 0.875rem;
  padding: 0.5rem 0.75rem;
  outline: none;
  transition: border-color var(--motion-duration) var(--motion-ease);
}
.plan-create-form__input:focus {
  border-color: var(--color-accent);
}
.plan-create-form__input.is-error {
  border-color: var(--color-danger, #b3563e);
}
.plan-create-form__task-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.plan-create-form__task-title {
  flex: 1;
}
.plan-create-form__task-due {
  width: 8.5rem;
}
.plan-create-form__remove {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  padding: 0.375rem;
  border-radius: 0.375rem;
}
.plan-create-form__remove:hover {
  color: var(--color-danger, #b3563e);
  background: color-mix(in srgb, var(--color-danger, #b3563e) 8%, transparent);
}
.plan-create-form__add-task {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  align-self: flex-start;
  border: 1px dashed var(--color-border);
  border-radius: 0.5rem;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 0.8125rem;
  padding: 0.375rem 0.75rem;
  cursor: pointer;
}
.plan-create-form__add-task:hover {
  color: var(--color-accent);
  border-color: var(--color-accent);
}
.plan-create-form__actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}
/* 周期三选项（无 / 每日 / 每周） */
.plan-create-form__seg {
  display: inline-flex;
  gap: 0.375rem;
}
.seg-btn {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-button);
  background: transparent;
  color: var(--color-text-secondary);
  font-family: var(--font-ui);
  font-size: 0.8125rem;
  padding: 0.375rem 0.75rem;
  cursor: pointer;
}
.seg-btn.is-active {
  border-color: var(--color-accent);
  color: var(--color-accent);
}
/* 每周时选择的周几 chip（可多选） */
.plan-create-form__weekdays {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  flex-wrap: wrap;
  margin-top: 0.375rem;
}
.plan-create-form__weekday-label {
  font-size: 0.75rem;
  color: var(--color-text-faint);
}
.weekday-chip {
  border: 1px solid var(--color-border);
  border-radius: 999px;
  background: transparent;
  color: var(--color-text-secondary);
  font-family: var(--font-ui);
  font-size: 0.75rem;
  padding: 0.25rem 0.625rem;
  cursor: pointer;
}
.weekday-chip.is-active {
  border-color: var(--color-accent);
  background: var(--color-accent);
  color: var(--color-bg);
}
/* 目标值一行三输入：数值 / 单位 / 周期 */
.plan-create-form__target-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.plan-create-form__target-value {
  width: 6rem;
}
.plan-create-form__target-unit {
  width: 9rem;
}
.plan-create-form__target-period {
  width: 7rem;
}
</style>
