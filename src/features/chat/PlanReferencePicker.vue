<script setup lang="ts">
import { computed, ref } from 'vue'

import type { PlanItem } from '@/shared/api/plan'
import { chatCopy } from '@/shared/copy/chat'

const props = withDefaults(
  defineProps<{
    modelValue: string[]
    plans: PlanItem[]
    max?: number
    loading?: boolean
  }>(),
  {
    loading: false,
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: string[]]
}>()

const open = ref(false)

const maxCount = computed(() => props.max ?? 3)
const selectedIds = computed(() => props.modelValue)

/* 只列进行中的计划：已归档/已完成的不再附信 */
const activePlans = computed(() =>
  props.plans.filter((plan) => plan.status === 'active'),
)

function planProgress(plan: PlanItem): { done: number; total: number } {
  const tasks = plan.tasks ?? []
  const done = tasks.filter((task) => task.status === 'done').length
  return { done, total: tasks.length }
}

function planById(planId: string): PlanItem | undefined {
  return activePlans.value.find((plan) => plan.id === planId)
}

function togglePlan(planId: string) {
  if (selectedIds.value.includes(planId)) {
    emit(
      'update:modelValue',
      selectedIds.value.filter((id) => id !== planId),
    )
    return
  }
  if (selectedIds.value.length >= maxCount.value) return
  emit('update:modelValue', [...selectedIds.value, planId])
}

function removePin(planId: string) {
  emit(
    'update:modelValue',
    selectedIds.value.filter((id) => id !== planId),
  )
}

function chipLabel(planId: string): string {
  const plan = planById(planId)
  return plan ? plan.title : `#${planId.slice(0, 6)}`
}

function planMeta(plan: PlanItem): string {
  const { done, total } = planProgress(plan)
  const parts: string[] = []
  if (total > 0) parts.push(`${done}/${total}`)
  if (plan.recurrence) parts.push(plan.recurrence)
  if (plan.target_value != null) {
    const unit = plan.target_unit ?? ''
    parts.push(`目标 ${plan.target_value}${unit}`)
  }
  return parts.join(' · ')
}
</script>

<template>
  <section class="plan-picker">
    <div class="plan-picker__selected">
      <button
        v-for="id in selectedIds"
        :key="id"
        type="button"
        class="plan-picker__chip"
        :title="chatCopy.removePlanPin"
        data-testid="plan-picker__chip"
        @click="removePin(id)"
      >
        {{ chipLabel(id) }}
        <span aria-hidden="true">×</span>
      </button>
      <button
        type="button"
        class="plan-picker__add"
        :class="{ 'is-open': open }"
        :disabled="selectedIds.length >= maxCount"
        data-testid="plan-picker__add"
        @click="open = !open"
      >
        + {{ chatCopy.pickPlan }}
      </button>
    </div>

    <div v-if="open" class="plan-picker__panel">
      <p class="plan-picker__hint">{{ chatCopy.pickPlanHint }}</p>
      <p v-if="loading" class="plan-picker__empty">{{ chatCopy.pickPlanEmpty }}</p>
      <p v-else-if="activePlans.length === 0" class="plan-picker__empty">
        {{ chatCopy.pickPlanEmpty }}
      </p>
      <div v-else class="plan-picker__list">
        <button
          v-for="plan in activePlans"
          :key="plan.id"
          type="button"
          class="plan-picker__item"
          :class="{ 'is-selected': selectedIds.includes(plan.id) }"
          :aria-pressed="selectedIds.includes(plan.id)"
          data-testid="plan-picker__item"
          @click="togglePlan(plan.id)"
        >
          <span class="plan-picker__title">{{ plan.title }}</span>
          <span v-if="planMeta(plan)" class="plan-picker__meta">{{ planMeta(plan) }}</span>
          <span
            v-if="plan.motivation?.trim()"
            class="plan-picker__summary"
          >
            {{ plan.motivation.trim() }}
          </span>
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.plan-picker {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.plan-picker__selected {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
}

.plan-picker__chip,
.plan-picker__add {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.625rem;
  border-radius: 999px;
  border: 1px solid var(--color-border);
  background: var(--color-bg-elevated);
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition:
    border-color var(--motion-duration) var(--motion-ease),
    background var(--motion-duration) var(--motion-ease),
    color var(--motion-duration) var(--motion-ease);
}

.plan-picker__add:hover:not(:disabled),
.plan-picker__add.is-open {
  border-color: color-mix(in srgb, var(--color-accent) 35%, var(--color-border));
  color: var(--color-text-primary);
}

.plan-picker__chip {
  border-color: color-mix(in srgb, var(--color-accent) 45%, var(--color-border));
  background: color-mix(in srgb, var(--color-accent) 12%, var(--color-bg-elevated));
  color: var(--color-text-primary);
}

.plan-picker__panel {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  max-height: 14rem;
  overflow-y: auto;
  padding: 0.625rem;
  border: 1px solid var(--color-border);
  border-radius: 0.625rem;
  background: color-mix(in srgb, var(--color-bg-elevated) 80%, transparent);
}

.plan-picker__hint,
.plan-picker__empty {
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
}

.plan-picker__list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.plan-picker__item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.25rem;
  width: 100%;
  padding: 0.625rem 0.75rem;
  border-radius: 0.5rem;
  border: 1px solid var(--color-border);
  background: var(--color-bg-elevated);
  text-align: left;
  cursor: pointer;
  transition:
    border-color var(--motion-duration) var(--motion-ease),
    background var(--motion-duration) var(--motion-ease),
    box-shadow var(--motion-duration) var(--motion-ease);
}

.plan-picker__item:hover {
  border-color: color-mix(in srgb, var(--color-accent) 30%, var(--color-border));
  background: var(--color-bg-elevated-2);
}

.plan-picker__item.is-selected {
  border-color: color-mix(in srgb, var(--color-accent) 50%, var(--color-border));
  background: color-mix(in srgb, var(--color-accent) 10%, var(--color-bg-elevated));
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--color-accent) 20%, transparent);
}

.plan-picker__title {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.8125rem;
  color: var(--color-text-primary);
}

.plan-picker__meta {
  font-size: 0.625rem;
  color: var(--color-accent);
  font-weight: 600;
}

.plan-picker__summary {
  font-size: 0.75rem;
  line-height: 1.45;
  color: var(--color-text-secondary);
}
</style>
