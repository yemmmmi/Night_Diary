<script setup lang="ts">
import { computed } from 'vue'

import type { MemoryCard } from '@/shared/api/card'
import { cardCopy, emotionPromptFor } from '@/shared/copy/card'
import { emotionIconFor } from '@/shared/utils/emotionIcon'

const props = defineProps<{
  card: MemoryCard
}>()

const emotions = computed(() => {
  const fromList = (props.card.emotions || []).filter(Boolean)
  if (fromList.length > 0) return fromList
  return props.card.emotion ? [props.card.emotion] : []
})
</script>

<template>
  <section class="card-diary-prompt" aria-label="记忆卡片续写引导">
    <p class="card-diary-prompt__badge">{{ cardCopy.cardOriginBadge }}</p>

    <div v-if="card.event_summary" class="card-diary-prompt__event">
      <p class="card-diary-prompt__event-label">{{ cardCopy.eventNoteLabel }}</p>
      <p class="card-diary-prompt__event-text font-diary">{{ card.event_summary }}</p>
    </div>

    <div class="card-diary-prompt__clouds">
      <div
        v-for="emotion in emotions"
        :key="emotion"
        class="emotion-cloud"
      >
        <div class="emotion-cloud__head">
          <component :is="emotionIconFor(emotion)" :size="16" weight="duotone" class="emotion-cloud__icon" />
          <span class="emotion-cloud__label">{{ emotion }}</span>
        </div>
        <p class="emotion-cloud__prompt">{{ emotionPromptFor(emotion) }}</p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.card-diary-prompt {
  margin-bottom: 1rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--color-border);
}

.card-diary-prompt__badge {
  display: inline-block;
  font-size: 0.6875rem;
  font-weight: 600;
  color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 10%, transparent);
  padding: 0.1875rem 0.5rem;
  border-radius: 999px;
  margin-bottom: 0.75rem;
}

.card-diary-prompt__event {
  margin-bottom: 0.75rem;
  padding: 0.625rem 0.75rem;
  border-radius: 0.75rem;
  background: color-mix(in srgb, var(--color-accent) 6%, var(--color-bg-elevated));
  border: 1px solid color-mix(in srgb, var(--color-accent) 18%, var(--color-border));
}

.card-diary-prompt__event-label {
  font-size: 0.6875rem;
  font-weight: 600;
  color: var(--color-text-secondary);
  margin-bottom: 0.25rem;
}

.card-diary-prompt__event-text {
  font-size: 0.875rem;
  line-height: 1.55;
  color: var(--color-text-primary);
}

.card-diary-prompt__clouds {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.emotion-cloud {
  flex: 1 1 10rem;
  max-width: 100%;
  padding: 0.625rem 0.75rem;
  border-radius: 1.25rem 1.25rem 1.25rem 0.375rem;
  background: color-mix(in srgb, var(--color-bg-elevated) 85%, var(--color-accent) 8%);
  border: 1px solid color-mix(in srgb, var(--color-border) 80%, var(--color-accent) 20%);
  box-shadow: 0 2px 8px color-mix(in srgb, var(--color-accent) 8%, transparent);
}

.emotion-cloud__head {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  margin-bottom: 0.375rem;
}

.emotion-cloud__icon {
  color: var(--color-accent);
  flex-shrink: 0;
}

.emotion-cloud__label {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.emotion-cloud__prompt {
  font-size: 0.75rem;
  line-height: 1.5;
  color: var(--color-text-secondary);
}
</style>
