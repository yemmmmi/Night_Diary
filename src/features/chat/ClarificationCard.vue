<template>
  <div class="clarification-card">
    <div class="card-icon">💬</div>
    <p class="question">{{ clarification.question }}</p>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  clarification: {
    question: string
    missing_fields?: string[]
    context?: Record<string, unknown>
  }
}>()
</script>

<style scoped>
.clarification-card {
  border-left: 3px solid var(--color-accent);
  padding: 8px 12px;
  margin: 8px 0;
  background: var(--color-bg-elevated-2, #f9fafb);
  border-radius: 0 8px 8px 0;
}

.card-icon {
  font-size: 14px;
}

.question {
  font-size: 14px;
  color: var(--color-text-secondary, #52525b);
  margin: 4px 0 0;
  line-height: 1.5;
}
</style>
