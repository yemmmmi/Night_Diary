<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { PhPlus } from '@phosphor-icons/vue'

import PlanCreateForm from '@/features/plan/PlanCreateForm.vue'
import PlanRefsBlock from '@/features/plan/PlanRefsBlock.vue'
import GameButton from '@/shared/components/GameButton.vue'
import GlassPanel from '@/shared/components/GlassPanel.vue'
import { planCopy } from '@/shared/copy/plan'
import { usePlanStore } from '@/stores/plan'
import { toIsoDate } from '@/shared/utils/diaryFormat'

defineOptions({ name: 'PlanScene' })

const router = useRouter()
const planStore = usePlanStore()

const todayIso = computed(() => toIsoDate(new Date()))
const showCreateForm = ref(false)
const newTaskTitle = ref('')

function isOverdue(dueDate: string | null, status: string): boolean {
  return Boolean(dueDate) && dueDate! < todayIso.value && status !== 'done'
}

function goToChat() {
  router.push('/chat')
}

function startManualCreate() {
  showCreateForm.value = true
}

async function addTodayTask() {
  const title = newTaskTitle.value.trim()
  if (!title) return
  const ok = await planStore.createTodayTask(title, todayIso.value)
  if (ok) newTaskTitle.value = ''
}

onMounted(() => {
  planStore.loadPlans()
  planStore.loadTodayTasks()
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
      <h3 class="plan-scene__section-title">{{ planCopy.todayTitle }}</h3>
      <template v-if="planStore.todayTasks.length === 0">
        <GlassPanel class="plan-scene__empty" padding>
          <div class="plan-scene__empty-icon" aria-hidden="true">
            <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
              <circle cx="20" cy="20" r="16" stroke="currentColor" stroke-width="2" opacity="0.3" />
              <path d="M14 20l4 4 8-8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" opacity="0.5" />
            </svg>
          </div>
          <p class="plan-scene__empty-text">{{ planCopy.todayEmpty }}</p>
          <div class="plan-scene__quick-add">
            <input
              v-model="newTaskTitle"
              type="text"
              data-testid="today-add-input"
              class="plan-scene__quick-input"
              :placeholder="planCopy.todayAddPlaceholder"
              maxlength="200"
              @keydown.enter.prevent="addTodayTask"
            />
            <GameButton variant="secondary" data-testid="today-add-btn" @click="addTodayTask">
              {{ planCopy.todayAddCta }}
            </GameButton>
          </div>
        </GlassPanel>
      </template>
      <template v-else>
        <GlassPanel class="plan-scene__panel" padding>
          <div
            v-for="task in planStore.todayTasks"
            :key="task.id"
            class="task-row"
            :class="{ 'is-overdue': isOverdue(task.due_date, task.status) }"
          >
            <input
              type="checkbox"
              :checked="task.status === 'done'"
              @change="planStore.toggleTask(task.id, task.status)"
            />
            <span :class="{ done: task.status === 'done' }">{{ task.title }}</span>
            <span v-if="task.due_date" class="due">{{ task.due_date }}</span>
            <button class="btn-del" @click="planStore.removeTask(task.id)">×</button>
          </div>
          <div class="plan-scene__quick-add plan-scene__quick-add--inline">
            <input
              v-model="newTaskTitle"
              type="text"
              data-testid="today-add-input"
              class="plan-scene__quick-input"
              :placeholder="planCopy.todayAddPlaceholder"
              maxlength="200"
              @keydown.enter.prevent="addTodayTask"
            />
            <GameButton variant="ghost" data-testid="today-add-btn" @click="addTodayTask">
              <PhPlus :size="14" />
              {{ planCopy.todayAddCta }}
            </GameButton>
          </div>
        </GlassPanel>
      </template>
    </section>

    <section class="plan-scene__section">
      <h3 class="plan-scene__section-title">{{ planCopy.plansTitle }}</h3>
      <GlassPanel v-if="planStore.plans.length === 0" class="plan-scene__empty" padding>
        <div class="plan-scene__empty-icon" aria-hidden="true">
          <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
            <rect x="8" y="8" width="24" height="24" rx="4" stroke="currentColor" stroke-width="2" opacity="0.3" />
            <path d="M8 16h24M16 8v24" stroke="currentColor" stroke-width="2" opacity="0.3" />
            <circle cx="20" cy="22" r="4" stroke="currentColor" stroke-width="2" opacity="0.5" />
          </svg>
        </div>
        <p class="plan-scene__empty-text">{{ planCopy.plansEmpty }}</p>
        <div class="plan-scene__empty-actions">
          <GameButton variant="primary" data-testid="plans-empty-manual" @click="startManualCreate">
            {{ planCopy.plansEmptyCta }}
          </GameButton>
          <GameButton variant="ghost" data-testid="plans-empty-ai" @click="goToChat">
            {{ planCopy.plansEmptyAiCta }}
          </GameButton>
        </div>
      </GlassPanel>
      <div v-else class="plan-list">
        <GlassPanel
          v-for="plan in planStore.plans"
          :key="plan.id"
          class="plan-card"
          padding
        >
          <div class="plan-header">
            <span class="plan-title">{{ plan.title }}</span>
            <span v-if="plan.source === 'agent'" class="badge-agent">{{ planCopy.aiBadge }}</span>
            <button class="btn-del" @click="planStore.removePlan(plan.id)">{{ planCopy.delete }}</button>
          </div>
          <p v-if="plan.motivation" class="plan-motivation">{{ plan.motivation }}</p>
          <PlanRefsBlock :refs="plan.source_refs" />
          <div class="plan-progress">
            {{ plan.tasks.filter((t) => t.status === 'done').length }}/{{
              plan.tasks.length
            }}
          </div>
          <ul class="plan-tasks">
            <li v-for="task in plan.tasks" :key="task.id">
              <input
                type="checkbox"
                :checked="task.status === 'done'"
                @change="planStore.toggleTask(task.id, task.status)"
              />
              <span :class="{ done: task.status === 'done' }">{{ task.title }}</span>
            </li>
          </ul>
        </GlassPanel>
      </div>
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
  margin-bottom: 1.5rem;
}

.plan-scene__title {
  font-family: var(--font-ui);
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--color-text-primary);
  margin: 0;
}

.plan-scene__form {
  margin-bottom: 1.5rem;
}

.plan-scene__section {
  margin-bottom: 2rem;
}

.plan-scene__section-title {
  font-family: var(--font-ui);
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text-secondary);
  margin: 0 0 0.75rem;
  display: flex;
  align-items: center;
  gap: 0.375rem;
}

.plan-scene__section-title::before {
  content: '';
  width: 3px;
  height: 1rem;
  border-radius: 2px;
  background: var(--color-accent);
}

.plan-scene__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.625rem;
  padding: 2.5rem 1.5rem !important;
  text-align: center;
}

.plan-scene__empty-icon {
  color: var(--color-accent);
  opacity: 0.6;
  margin-bottom: 0.25rem;
}

.plan-scene__empty-text {
  margin: 0 0 0.875rem;
  font-size: 0.875rem;
  color: var(--color-text-secondary);
  line-height: 1.6;
}

.plan-scene__empty-actions {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
  justify-content: center;
}

.plan-scene__quick-add {
  display: flex;
  gap: 0.5rem;
  width: 100%;
  max-width: 26rem;
}

.plan-scene__quick-add--inline {
  margin-top: 0.75rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--color-border);
}

.plan-scene__quick-input {
  flex: 1;
  min-width: 0;
  border: 1px solid var(--color-border);
  border-radius: 0.5rem;
  background: var(--color-bg);
  color: var(--color-text-primary);
  font-size: 0.875rem;
  padding: 0.5rem 0.75rem;
  outline: none;
  transition: border-color var(--motion-duration) var(--motion-ease);
}

.plan-scene__quick-input:focus {
  border-color: var(--color-accent);
}

.plan-scene__panel {
  display: flex;
  flex-direction: column;
}

.task-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.625rem 0;
  border-bottom: 1px solid var(--color-border, #f4f4f5);
  font-size: 0.875rem;
}

.task-row:last-of-type {
  border-bottom: none;
}

.task-row.is-overdue {
  opacity: 0.65;
}

.task-row.is-overdue .due {
  color: var(--color-text-secondary, #a1a1aa);
}

.done {
  text-decoration: line-through;
  color: var(--color-text-secondary, #a1a1aa);
}

.due {
  font-size: 0.75rem;
  color: var(--color-text-secondary, #71717a);
  margin-left: auto;
}

.btn-del {
  background: none;
  border: none;
  color: var(--color-text-secondary, #d4d4d8);
  cursor: pointer;
  font-size: 1.125rem;
  line-height: 1;
  padding: 0 0.25rem;
}

.btn-del:hover {
  color: var(--color-danger, #ef4444);
}

.plan-card {
  margin-bottom: 0.75rem;
}

.plan-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.plan-title {
  font-weight: 600;
  font-size: 0.9375rem;
  flex: 1;
}

.badge-agent {
  background: color-mix(in srgb, var(--color-accent) 15%, transparent);
  color: var(--color-accent);
  font-size: 0.6875rem;
  font-weight: 600;
  padding: 0.125rem 0.5rem;
  border-radius: 999px;
}

.plan-motivation {
  font-size: 0.8125rem;
  color: var(--color-text-secondary, #52525b);
  margin: 0.5rem 0;
  line-height: 1.6;
}

.plan-progress {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-accent);
  margin-top: 0.5rem;
}

.plan-tasks {
  list-style: none;
  padding: 0;
  margin: 0.5rem 0 0;
}

.plan-tasks li {
  padding: 0.25rem 0;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8125rem;
}
</style>
