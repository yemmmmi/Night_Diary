<script setup lang="ts">
import { memoryCopy as copy } from '@/shared/copy/memory'
import type { PersonalityPreset } from '@/shared/api/memory'

const props = defineProps<{
  presets: PersonalityPreset[]
  current: string
  saving?: boolean
}>()

const emit = defineEmits<{ select: [key: string] }>()

function onSelect(key: string) {
  if (key === props.current || props.saving) return
  emit('select', key)
}
</script>

<template>
  <div class="personality" data-testid="personality-picker">
    <button
      v-for="preset in presets"
      :key="preset.key"
      type="button"
      class="personality__card"
      :class="{ 'personality__card--active': preset.key === current }"
      :disabled="saving"
      :data-testid="`personality-${preset.key}`"
      @click="onSelect(preset.key)"
    >
      <span class="personality__name">{{ preset.label }}</span>
      <span class="personality__len">
        {{ copy.personalityLength(preset.min_chars, preset.max_chars) }}
      </span>
    </button>
  </div>
</template>

<style scoped>
.personality {
  display: flex;
  flex-wrap: wrap;
  gap: 0.625rem;
}

.personality__card {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-width: 7.5rem;
  padding: 0.625rem 0.875rem;
  border: 1px solid var(--color-line);
  border-radius: var(--radius-seal);
  background: transparent;
  text-align: left;
  cursor: pointer;
  transition:
    border-color var(--dur-fast) var(--ease-out-quart),
    color var(--dur-fast) var(--ease-out-quart);
}

.personality__card:disabled {
  opacity: 0.6;
  cursor: default;
}

.personality__card:not(:disabled):hover {
  border-color: var(--color-accent);
}

.personality__card--active {
  border-color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 8%, transparent);
}

.personality__name {
  font-size: 0.875rem;
  color: var(--color-text-primary);
}

.personality__card--active .personality__name {
  color: var(--color-accent);
  font-weight: 600;
}

.personality__len {
  font-size: 0.6875rem;
  font-variant-numeric: tabular-nums;
  color: var(--color-text-faint);
}
</style>