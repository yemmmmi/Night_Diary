<script setup lang="ts">
import { computed, ref } from 'vue'

import type { Tag } from '@/shared/api/tags'
import { chatCopy } from '@/shared/copy/chat'

const props = withDefaults(
  defineProps<{
    modelValue: string[]
    tags: Tag[]
    max?: number
    loading?: boolean
  }>(),
  {
    tags: () => [],
    loading: false,
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: string[]]
}>()

const open = ref(false)

const maxCount = computed(() => props.max ?? 3)
const selectedNames = computed(() => props.modelValue)

/* 只列有日记的标签：空标签引用没有可注入的上下文 */
const usableTags = computed(() =>
  [...props.tags]
    .filter((tag) => tag.usage_count > 0)
    .sort((a, b) => b.usage_count - a.usage_count),
)

function toggleTag(name: string) {
  if (selectedNames.value.includes(name)) {
    emit(
      'update:modelValue',
      selectedNames.value.filter((item) => item !== name),
    )
    return
  }
  if (selectedNames.value.length >= maxCount.value) return
  emit('update:modelValue', [...selectedNames.value, name])
}

function removePin(name: string) {
  emit(
    'update:modelValue',
    selectedNames.value.filter((item) => item !== name),
  )
}

function tagColor(name: string): string | undefined {
  return props.tags.find((tag) => tag.name === name)?.color
}
</script>

<template>
  <section class="tag-picker">
    <div class="tag-picker__selected">
      <button
        v-for="name in selectedNames"
        :key="name"
        type="button"
        class="tag-picker__chip"
        :style="tagColor(name) ? { '--tag-color': tagColor(name) } : undefined"
        :title="chatCopy.removeTagPin"
        data-testid="tag-picker__chip"
        @click="removePin(name)"
      >
        #{{ name }}
        <span aria-hidden="true">×</span>
      </button>
      <button
        type="button"
        class="tag-picker__add"
        :class="{ 'is-open': open }"
        :disabled="selectedNames.length >= maxCount || usableTags.length === 0"
        data-testid="tag-picker__add"
        @click="open = !open"
      >
        + {{ chatCopy.pickTag }}
      </button>
    </div>

    <div v-if="open" class="tag-picker__panel">
      <p class="tag-picker__hint">{{ chatCopy.pickTagHint }}</p>
      <p v-if="loading" class="tag-picker__empty">{{ chatCopy.pickTagEmpty }}</p>
      <p v-else-if="usableTags.length === 0" class="tag-picker__empty">
        {{ chatCopy.pickTagEmpty }}
      </p>
      <div v-else class="tag-picker__list">
        <button
          v-for="tag in usableTags"
          :key="tag.id"
          type="button"
          class="tag-picker__item"
          :class="{ 'is-selected': selectedNames.includes(tag.name) }"
          :aria-pressed="selectedNames.includes(tag.name)"
          data-testid="tag-picker__item"
          @click="toggleTag(tag.name)"
        >
          <span class="tag-picker__name">
            <span class="tag-picker__dot" :style="{ background: tag.color }" aria-hidden="true" />
            #{{ tag.name }}
          </span>
          <span class="tag-picker__meta">{{ tag.usage_count }} 篇</span>
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.tag-picker {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.tag-picker__selected {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
}

.tag-picker__chip,
.tag-picker__add {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.625rem;
  border-radius: 999px;
  border: 1px solid var(--color-border);
  background: var(--color-bg-elevated);
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition:
    border-color var(--motion-duration) var(--motion-ease),
    background var(--motion-duration) var(--motion-ease),
    color var(--motion-duration) var(--motion-ease);
}

.tag-picker__add:hover:not(:disabled),
.tag-picker__add.is-open {
  border-color: color-mix(in srgb, var(--color-accent) 35%, var(--color-border));
  color: var(--color-text-primary);
}

.tag-picker__chip {
  border-color: color-mix(
    in srgb,
    var(--tag-color, var(--color-accent)) 45%,
    var(--color-border)
  );
  background: color-mix(
    in srgb,
    var(--tag-color, var(--color-accent)) 12%,
    var(--color-bg-elevated)
  );
  color: var(--color-text-primary);
}

.tag-picker__panel {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  max-height: 14rem;
  overflow-y: auto;
  padding: 0.625rem;
  border: 1px solid var(--color-border);
  border-radius: 0.625rem;
  background: color-mix(in srgb, var(--color-bg-elevated) 80%, transparent);
}

.tag-picker__hint,
.tag-picker__empty {
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
}

.tag-picker__list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.tag-picker__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  width: 100%;
  padding: 0.5rem 0.75rem;
  border-radius: 0.5rem;
  border: 1px solid var(--color-border);
  background: var(--color-bg-elevated);
  text-align: left;
  cursor: pointer;
  transition:
    border-color var(--motion-duration) var(--motion-ease),
    background var(--motion-duration) var(--motion-ease),
    box-shadow var(--motion-duration) var(--motion-ease);
}

.tag-picker__item:hover {
  border-color: color-mix(in srgb, var(--color-accent) 30%, var(--color-border));
  background: var(--color-bg-elevated-2);
}

.tag-picker__item.is-selected {
  border-color: color-mix(in srgb, var(--color-accent) 50%, var(--color-border));
  background: color-mix(in srgb, var(--color-accent) 10%, var(--color-bg-elevated));
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--color-accent) 20%, transparent);
}

.tag-picker__name {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.8125rem;
  color: var(--color-text-primary);
}

.tag-picker__dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 999px;
  flex: none;
}

.tag-picker__meta {
  font-size: 0.625rem;
  color: var(--color-text-secondary);
}
</style>