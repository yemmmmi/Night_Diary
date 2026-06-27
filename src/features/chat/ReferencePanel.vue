<script setup lang="ts">
import { chatCopy, type DiaryReferenceItem } from '@/shared/copy/chat'

defineProps<{
  pinnedDiaries: DiaryReferenceItem[]
  retrievedDiaries: DiaryReferenceItem[]
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
      <div v-if="pinnedDiaries.length > 0" class="ref-panel__block">
        <p class="ref-panel__label">{{ chatCopy.pinnedDiaries }}</p>
        <div
          v-for="item in pinnedDiaries"
          :key="`pin-${item.id}`"
          class="ref-panel__item"
        >
          <p class="ref-panel__item-title">#{{ item.id }} · {{ item.date ?? '未标注' }}</p>
          <p class="ref-panel__text">{{ item.summary }}</p>
        </div>
      </div>

      <div v-if="retrievedDiaries.length > 0" class="ref-panel__block">
        <p class="ref-panel__label">{{ chatCopy.retrievedDiaries }}</p>
        <div
          v-for="item in retrievedDiaries"
          :key="`ret-${item.id}`"
          class="ref-panel__item"
        >
          <p class="ref-panel__item-title">#{{ item.id }} · {{ item.date ?? '未标注' }}</p>
          <p class="ref-panel__text">{{ item.summary }}</p>
        </div>
      </div>

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

      <p
        v-if="pinnedDiaries.length === 0 && retrievedDiaries.length === 0 && episodicMemories.length === 0"
        class="ref-panel__empty"
      >
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
  margin-bottom: 0.375rem;
}

.ref-panel__item {
  margin-bottom: 0.5rem;
}

.ref-panel__item-title {
  font-size: 0.625rem;
  color: var(--color-text-secondary);
  margin-bottom: 0.125rem;
}

.ref-panel__text {
  font-size: 0.75rem;
  line-height: 1.5;
  color: var(--color-text-primary);
}

.ref-panel__text--mem {
  color: var(--color-text-secondary);
  margin-bottom: 0.25rem;
}
</style>
