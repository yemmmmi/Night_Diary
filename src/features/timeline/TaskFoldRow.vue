<script setup lang="ts">
import { computed, ref } from 'vue'
import { PhCaretDown } from '@phosphor-icons/vue'

import { timelineCopy as copy } from '@/shared/copy/timeline'
import { usePlanStore } from '@/stores/plan'

const planStore = usePlanStore()
const expanded = ref(false)

const total = computed(() => planStore.todayTasks.length)
const done = computed(() => planStore.todayTasks.filter((t) => t.status === 'done').length)
</script>

<template>
  <div v-if="total > 0" class="task-fold">
    <button type="button" class="task-fold__summary" @click="expanded = !expanded">
      <span>{{ copy.taskSummary(total, done) }}</span>
      <PhCaretDown :size="14" class="task-fold__caret" :class="{ 'is-open': expanded }" />
    </button>
    <div v-if="expanded" class="task-fold__list">
      <label v-for="task in planStore.todayTasks" :key="task.id" class="task-fold__item">
        <input
          type="checkbox"
          :checked="task.status === 'done'"
          @change="planStore.toggleTask(task.id, task.status)"
        />
        <span class="task-fold__title" :class="{ 'is-done': task.status === 'done' }">
          {{ task.title }}
        </span>
      </label>
    </div>
  </div>
</template>

<style scoped>
.task-fold {
  border: 1px solid var(--color-border);
  border-radius: 0.75rem;
  background: var(--color-bg-elevated);
  padding: 0.375rem 0.625rem;
}
.task-fold__summary {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: space-between;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 0.8125rem;
  cursor: pointer;
  padding: 0.25rem 0;
}
.task-fold__caret {
  transition: transform var(--motion-duration) var(--motion-ease);
}
.task-fold__caret.is-open {
  transform: rotate(180deg);
}
.task-fold__list {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding: 0.375rem 0 0.25rem;
  border-top: 1px solid var(--color-border);
}
.task-fold__item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8125rem;
  color: var(--color-text-primary);
  padding: 0.1875rem 0;
  cursor: pointer;
}
.task-fold__item input {
  accent-color: var(--color-accent);
}
.task-fold__title.is-done {
  color: var(--color-text-secondary);
  text-decoration: line-through;
}
</style>
