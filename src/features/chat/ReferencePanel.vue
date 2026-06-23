<script setup lang="ts">
import { chatCopy } from '@/shared/copy/chat'

defineProps<{
  recentDiarySummary: string | null
  episodicMemories: string[]
  loading?: boolean
}>()
</script>

<template>
  <section class="ref-panel">
    <h3 class="ref-panel__title">{{ chatCopy.referenceTitle }}</h3>

    <div v-if="loading" class="ref-panel__loading">
      <p>{{ chatCopy.noReference }}</p>
    </div>

    <template v-else>
      <!-- Recent diaries -->
      <div v-if="recentDiarySummary" class="ref-panel__block">
        <p class="ref-panel__label">{{ chatCopy.recentDiaries }}</p>
        <p class="ref-panel__text">{{ recentDiarySummary }}</p>
      </div>

      <!-- Episodic memory -->
      <div v-if="episodicMemories.length > 0" class="ref-panel__block">
        <p class="ref-panel__label">{{ chatCopy.episodicMemory }}</p>
        <p
          v-for="(mem, idx) in episodicMemories"
          :key="idx"
          class="ref-panel__text ref-panel__text--mem"
        >
          {{ mem }}
        </p>
      </div>

      <p v-if="!recentDiarySummary && episodicMemories.length === 0" class="ref-panel__empty">
        {{ chatCopy.noReference }}
      </p>
    </template>
  </section>
</template>

<style scoped>
.ref-panel {
  display: flex;
  flex-direction: column;
}

.ref-panel__title {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 0.625rem;
}

.ref-panel__loading,
.ref-panel__empty {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

.ref-panel__block {
  margin-bottom: 0.75rem;
  padding-bottom: 0.625rem;
  border-bottom: 1px solid var(--color-border);
}

.ref-panel__label {
  font-size: 0.6875rem;
  font-weight: 600;
  color: var(--color-accent);
  margin-bottom: 0.25rem;
}

.ref-panel__text {
  font-size: 0.75rem;
  line-height: 1.5;
  color: var(--color-text-secondary);
}

.ref-panel__text--mem {
  padding: 0.1875rem 0;
}
</style>
