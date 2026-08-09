<template>
  <div class="plan-scene">
    <h2>我的计划</h2>

    <section class="today-section">
      <h3>今日待办</h3>
      <div v-if="planStore.todayTasks.length === 0" class="empty">
        今天没有待办，享受当下吧
      </div>
      <div v-else>
        <div
          v-for="task in planStore.todayTasks"
          :key="task.id"
          class="task-row"
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
      <h3>计划</h3>
      <div v-if="planStore.plans.length === 0" class="empty">
        还没有计划，可以在对话中让 AI 帮你规划
      </div>
      <div v-else class="plan-list">
        <div v-for="plan in planStore.plans" :key="plan.id" class="plan-card">
          <div class="plan-header">
            <span class="plan-title">{{ plan.title }}</span>
            <span v-if="plan.source === 'agent'" class="badge-agent">AI 建议</span>
            <button class="btn-del" @click="planStore.removePlan(plan.id)">删除</button>
          </div>
          <p v-if="plan.motivation" class="plan-motivation">{{ plan.motivation }}</p>
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
import { onMounted } from 'vue'
import { usePlanStore } from '@/stores/plan'

defineOptions({ name: 'PlanScene' })

const planStore = usePlanStore()

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
