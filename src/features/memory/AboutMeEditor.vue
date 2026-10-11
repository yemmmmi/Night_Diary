<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { PhCheck } from '@phosphor-icons/vue'

import { memoryCopy as copy } from '@/shared/copy/memory'

const props = defineProps<{
  content: string
  maxChars: number
  saving?: boolean
}>()

const emit = defineEmits<{ save: [content: string] }>()

const draft = ref(props.content)
const saved = ref(false)

watch(
  () => props.content,
  (value) => {
    draft.value = value
  },
)

const trimmed = computed(() => draft.value.trim())
const dirty = computed(() => trimmed.value !== props.content.trim())
const canSave = computed(() => dirty.value && !props.saving)
const showSaved = computed(() => saved.value && !dirty.value && !props.saving)

watch(dirty, (isDirty) => {
  if (isDirty) saved.value = false
})

function onSave() {
  if (!canSave.value) return
  emit('save', trimmed.value)
  saved.value = true
}
</script>

<template>
  <div class="about-me">
    <textarea
      v-model="draft"
      class="about-me__input"
      data-testid="about-input"
      :maxlength="maxChars"
      :placeholder="copy.aboutPlaceholder"
      rows="4"
    />
    <div class="about-me__foot">
      <span class="about-me__count" data-testid="about-counter">
        {{ copy.aboutCharCount(draft.length, maxChars) }}
      </span>
      <span v-if="showSaved" class="about-me__status" data-testid="about-status">
        {{ copy.aboutSaved }}
      </span>
      <span v-else-if="dirty" class="about-me__status" data-testid="about-status">
        {{ copy.aboutDirty }}
      </span>
      <button
        type="button"
        class="about-me__save"
        data-testid="about-save"
        :disabled="!canSave"
        @click="onSave"
      >
        <PhCheck :size="14" />
        {{ saving ? copy.aboutSaving : copy.aboutSave }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.about-me {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.about-me__input {
  width: 100%;
  resize: vertical;
  min-height: 5.5rem;
  padding: 0.625rem 0.75rem;
  border: 1px solid var(--color-line);
  border-radius: var(--radius-seal);
  background: var(--color-surface-sunken, transparent);
  color: var(--color-text-primary);
  font-family: inherit;
  font-size: 0.875rem;
  line-height: 1.7;
}

.about-me__input::placeholder {
  color: var(--color-text-faint);
}

.about-me__input:focus {
  outline: none;
  border-color: var(--color-accent);
}

.about-me__foot {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.about-me__count {
  font-size: 0.6875rem;
  font-variant-numeric: tabular-nums;
  color: var(--color-text-faint);
}

.about-me__status {
  font-size: 0.6875rem;
  color: var(--color-text-faint);
}

.about-me__save {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.375rem 0.875rem;
  border: 1px solid var(--color-line);
  border-radius: var(--radius-button);
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 0.75rem;
  cursor: pointer;
  transition: color var(--dur-fast) var(--ease-out-quart);
}

.about-me__save:disabled {
  opacity: 0.5;
  cursor: default;
}

.about-me__save:not(:disabled):hover {
  color: var(--color-accent);
  border-color: var(--color-accent);
}
</style>