<template>
  <div class="plan-scene">
    <h2>{{ planCopy.title }}</h2>

    <section class="today-section">
      <h3>{{ planCopy.todayTitle }}</h3>
      <div v-if="planStore.todayTasks.length === 0" class="empty">
        {{ planCopy.todayEmpty }}
      </div>
      <div v-else>
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
      </div>
    </section>

    <section class="plans-section">
      <h3>{{ planCopy.plansTitle }}</h3>
      <div v-if="planStore.plans.length === 0" class="empty">
        {{ planCopy.plansEmpty }}
      </div>
      <div v-else class="plan-list">
        <div v-for="plan in planStore.plans" :key="plan.id" class="plan-card">
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
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'

import PlanRefsBlock from '@/features/plan/PlanRefsBlock.vue'
import { planCopy } from '@/shared/copy/plan'
import { usePlanStore } from '@/stores/plan'
import { toIsoDate } from '@/shared/utils/diaryFormat'

defineOptions({ name: 'PlanScene' })

const planStore = usePlanStore()

const todayIso = computed(() => toIsoDate(new Date()))

function isOverdue(dueDate: string | null, status: string): boolean {
  return Boolean(dueDate) && dueDate! < todayIso.value && status !== 'done'
}

onMounted(() => {
  planStore.loadPlans()
  planStore.loadTodayTasks()
})
</script>

<style scoped>
.plan-scene {
  padding: 20px;
  max-width: 800px;
  margin: 0 auto;
  color: var(--color-text-primary);
}

h2 {
  margin-bottom: 20px;
}

h3 {
  font-size: 16px;
  color: var(--color-text-secondary, #52525b);
  margin: 20px 0 12px;
}

.empty {
  color: var(--color-text-secondary, #a1a1aa);
  font-size: 14px;
  padding: 16px 0;
}

.task-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
  border-bottom: 1px solid var(--color-border, #f4f4f5);
  font-size: 14px;
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
  font-size: 12px;
  color: var(--color-text-secondary, #71717a);
  margin-left: auto;
}

.btn-del {
  background: none;
  border: none;
  color: var(--color-text-secondary, #d4d4d8);
  cursor: pointer;
  font-size: 18px;
  line-height: 1;
}

.btn-del:hover {
  color: var(--color-danger, #ef4444);
}

.plan-card {
  border: 1px solid var(--color-border, #e4e4e7);
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 12px;
}

.plan-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.plan-title {
  font-weight: 600;
  flex: 1;
}

.badge-agent {
  background: color-mix(in srgb, var(--color-accent) 15%, transparent);
  color: var(--color-accent);
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
}

.plan-motivation {
  font-size: 13px;
  color: var(--color-text-secondary, #52525b);
  margin: 8px 0;
}

.plan-progress {
  font-size: 12px;
  color: var(--color-text-secondary, #71717a);
}

.plan-tasks {
  list-style: none;
  padding: 0;
  margin: 8px 0 0;
}

.plan-tasks li {
  padding: 4px 0;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}
</style>
