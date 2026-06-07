<script setup lang="ts">
import { computed } from 'vue'

export interface MoodOption {
  emoji: string
  label: string
  value: string
}

const props = withDefaults(
  defineProps<{
    modelValue?: string
    options?: MoodOption[]
  }>(),
  {
    modelValue: '',
    options: () => [
      { emoji: '😊', label: '开心', value: 'happy' },
      { emoji: '😢', label: '难过', value: 'sad' },
      { emoji: '😌', label: '平静', value: 'calm' },
      { emoji: '😤', label: '烦躁', value: 'frustrated' },
      { emoji: '🥱', label: '疲惫', value: 'tired' },
      { emoji: '🤔', label: '思考', value: 'thoughtful' },
    ],
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const selected = computed({
  get: () => props.modelValue,
  set: (value: string) => emit('update:modelValue', value),
})

function select(value: string) {
  selected.value = value
}
</script>

<template>
  <div class="mood-selector" role="listbox" aria-label="选择情绪">
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      role="option"
      :aria-selected="selected === option.value"
      class="mood-selector__item spotlight-border"
      :class="{ 'is-selected': selected === option.value }"
      :title="option.label"
      @click="select(option.value)"
    >
      <span class="mood-selector__emoji">{{ option.emoji }}</span>
      <span class="mood-selector__label">{{ option.label }}</span>
    </button>
  </div>
</template>

<style scoped>
.mood-selector {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.75rem;
}

@media (min-width: 640px) {
  .mood-selector {
    grid-template-columns: repeat(6, minmax(0, 1fr));
  }
}

.mood-selector__item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.35rem;
  padding: 0.75rem 0.5rem;
  border-radius: var(--radius-button);
  border: 1px solid var(--color-border);
  background: var(--color-bg-elevated);
  cursor: pointer;
  transition:
    transform var(--motion-duration) var(--motion-ease),
    border-color var(--motion-duration) var(--motion-ease),
    box-shadow var(--motion-duration) var(--motion-ease);
}

.mood-selector__item:hover {
  transform: translateY(-2px);
  border-color: color-mix(in srgb, var(--color-accent) 40%, var(--color-border));
}

.mood-selector__item.is-selected {
  border-color: var(--color-accent);
  box-shadow: 0 0 16px color-mix(in srgb, var(--color-accent) 30%, transparent);
  animation: mood-bounce 360ms var(--motion-ease);
}

.mood-selector__emoji {
  font-size: 1.5rem;
  line-height: 1;
}

.mood-selector__label {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

@keyframes mood-bounce {
  0% {
    transform: scale(1);
  }
  40% {
    transform: scale(1.08);
  }
  100% {
    transform: scale(1);
  }
}
</style>
