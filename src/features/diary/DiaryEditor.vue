<script setup lang="ts">
import { computed, onUnmounted, watch } from 'vue'

import { countWordUnits } from '@/shared/utils/diaryFormat'

const props = withDefaults(
  defineProps<{
    modelValue: string
    placeholder?: string
    readonly?: boolean
  }>(),
  {
    placeholder: '写下此刻的想法…',
    readonly: false,
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
  autosave: [value: string]
}>()

let autosaveTimer: ReturnType<typeof setTimeout> | null = null

const wordCount = computed(() => countWordUnits(props.modelValue))

watch(
  () => props.modelValue,
  (value) => {
    if (autosaveTimer) clearTimeout(autosaveTimer)
    autosaveTimer = setTimeout(() => {
      emit('autosave', value)
    }, 1000)
  },
)

// Clear pending autosave timer on unmount to prevent emit after destroy
onUnmounted(() => {
  if (autosaveTimer) {
    clearTimeout(autosaveTimer)
    autosaveTimer = null
  }
})

function onInput(event: Event) {
  const target = event.target as HTMLTextAreaElement
  emit('update:modelValue', target.value)
}

defineExpose({ wordCount })
</script>

<template>
  <div class="diary-editor">
    <textarea
      class="diary-editor__input font-diary"
      :value="modelValue"
      :placeholder="placeholder"
      :readonly="readonly"
      @input="onInput"
    />
  </div>
</template>

<style scoped>
.diary-editor {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}

.diary-editor__input {
  flex: 1;
  width: 100%;
  min-height: 12rem;
  resize: none;
  border: none;
  outline: none;
  background: transparent;
  color: var(--color-text-primary);
  font-size: 0.9375rem;
  line-height: 1.75;
  padding: 0;
}

.diary-editor__input::placeholder {
  color: var(--color-text-secondary);
  opacity: 0.7;
}
</style>
