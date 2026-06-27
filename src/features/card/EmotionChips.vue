<script setup lang="ts">
/**
 * EmotionChips — renders a card's emotions as icon chips.
 * Falls back to the single `emotion` field for legacy cards.
 */
import { computed } from 'vue'

import { emotionIconFor } from '@/shared/utils/emotionIcon'

const props = withDefaults(
  defineProps<{
    emotions?: string[] | null
    emotion?: string | null
    size?: number
    /** Kanban / tight spaces: icon only, no text label */
    compact?: boolean
    /** Cap visible chips (kanban shows primary emotion only) */
    maxCount?: number
  }>(),
  {
    emotions: null,
    emotion: null,
    size: 14,
    compact: false,
    maxCount: undefined,
  },
)

const list = computed<string[]>(() => {
  const fromList = (props.emotions || []).filter(Boolean)
  const base = fromList.length > 0 ? fromList : props.emotion ? [props.emotion] : []
  if (props.maxCount != null && props.maxCount > 0) {
    return base.slice(0, props.maxCount)
  }
  return base
})
</script>

<template>
  <div class="emotion-chips" :class="{ 'emotion-chips--compact': compact }">
    <span v-for="key in list" :key="key" class="emotion-chips__item">
      <component :is="emotionIconFor(key)" :size="size" weight="fill" />
      <span v-if="!compact" class="emotion-chips__label">{{ key }}</span>
    </span>
  </div>
</template>

<style scoped>
.emotion-chips {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.375rem;
}

.emotion-chips__item {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.1875rem 0.5rem;
  border-radius: 1rem;
  font-family: var(--font-ui);
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-accent) 28%, transparent);
}

.emotion-chips--compact .emotion-chips__item {
  padding: 0.125rem;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
}

.emotion-chips__label {
  white-space: nowrap;
}
</style>
