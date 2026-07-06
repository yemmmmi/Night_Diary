<script setup lang="ts">
import type { MiddlewareStatus } from '@/shared/api/dev'

defineProps<{
  status: MiddlewareStatus
}>()

const items = [
  { key: 'redis', label: 'Redis' },
  { key: 'neo4j', label: 'Neo4j' },
  { key: 'langgraph', label: 'LangGraph' },
  { key: 'rq', label: 'RQ' },
] as const
</script>

<template>
  <div class="middleware-status">
    <div v-for="item in items" :key="item.key" class="middleware-status__item">
      <span
        class="middleware-status__dot"
        :class="{ 'middleware-status__dot--active': status[item.key] }"
      />
      <span class="middleware-status__label">{{ item.label }}</span>
    </div>
  </div>
</template>

<style scoped>
.middleware-status {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.middleware-status__item {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}
.middleware-status__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-danger);
  opacity: 0.5;
}
.middleware-status__dot--active {
  background: var(--color-success);
  opacity: 1;
}
.middleware-status__label {
  font-size: 0.7rem;
  font-family: var(--font-mono);
  color: var(--color-text-secondary);
}
</style>
