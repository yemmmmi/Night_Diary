<script setup lang="ts">
import { chatCopy } from '@/shared/copy/chat'

defineProps<{
  cardSummary: string | null
  generating: boolean
  hasCards: boolean
}>()

defineEmits<{
  generateCard: []
}>()
</script>

<template>
  <section class="output-panel">
    <h3 class="output-panel__title">{{ chatCopy.outputTitle }}</h3>

    <div v-if="cardSummary" class="output-panel__card-preview">
      <p class="output-panel__card-text">{{ cardSummary }}</p>
    </div>

    <p v-else-if="hasCards" class="output-panel__info">{{ chatCopy.noCards }}</p>
    <p v-else class="output-panel__info">{{ chatCopy.noCards }}</p>

    <button
      type="button"
      class="output-panel__btn"
      :disabled="generating"
      @click="$emit('generateCard')"
    >
      {{ generating ? '生成中…' : chatCopy.generateCard }}
    </button>
  </section>
</template>

<style scoped>
.output-panel {
  display: flex;
  flex-direction: column;
}

.output-panel__title {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 0.625rem;
}

.output-panel__info {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  margin-bottom: 0.625rem;
}

.output-panel__card-preview {
  padding: 0.5rem 0.625rem;
  margin-bottom: 0.625rem;
  border-radius: 0.5rem;
  border: 1px solid var(--color-border);
  background: var(--color-bg-elevated-2);
}

.output-panel__card-text {
  font-size: 0.75rem;
  line-height: 1.5;
  color: var(--color-text-primary);
  white-space: pre-wrap;
}

.output-panel__btn {
  padding: 0.4375rem 0.75rem;
  border: 1px solid var(--color-accent);
  border-radius: 0.5rem;
  background: transparent;
  color: var(--color-accent);
  font-size: 0.75rem;
  font-weight: 500;
  cursor: pointer;
  transition: background var(--motion-duration) var(--motion-ease);
}

.output-panel__btn:hover:not(:disabled) {
  background: color-mix(in srgb, var(--color-accent) 10%, transparent);
}

.output-panel__btn:disabled {
  opacity: 0.5;
  cursor: default;
}
</style>
