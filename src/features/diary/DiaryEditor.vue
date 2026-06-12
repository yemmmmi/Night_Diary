<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import type { Tag } from '@/shared/api/tags'
import { countWordUnits } from '@/shared/utils/diaryFormat'

const props = withDefaults(
  defineProps<{
    modelValue: string
    tagIds?: number[]
    tags?: Tag[]
    placeholder?: string
    readonly?: boolean
  }>(),
  {
    tagIds: () => [],
    tags: () => [],
    placeholder: '写下此刻的想法…',
    readonly: false,
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'update:tagIds': [value: number[]]
  autosave: [value: string]
}>()

const selectedTagIds = ref<number[]>([...props.tagIds])
let autosaveTimer: ReturnType<typeof setTimeout> | null = null

const wordCount = computed(() => countWordUnits(props.modelValue))

watch(
  () => props.tagIds,
  (value) => {
    selectedTagIds.value = [...value]
  },
)

watch(
  () => props.modelValue,
  (value) => {
    if (autosaveTimer) clearTimeout(autosaveTimer)
    autosaveTimer = setTimeout(() => {
      emit('autosave', value)
    }, 1000)
  },
)

function onInput(event: Event) {
  const target = event.target as HTMLTextAreaElement
  emit('update:modelValue', target.value)
}

function toggleTag(tagId: number) {
  if (props.readonly) return
  const next = selectedTagIds.value.includes(tagId)
    ? selectedTagIds.value.filter((id) => id !== tagId)
    : [...selectedTagIds.value, tagId]
  selectedTagIds.value = next
  emit('update:tagIds', next)
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

    <footer class="diary-editor__footer">
      <div v-if="tags.length > 0" class="diary-editor__tags">
        <button
          v-for="tag in tags"
          :key="tag.id"
          type="button"
          class="diary-editor__tag"
          :class="{ 'is-selected': selectedTagIds.includes(tag.id) }"
          :style="{ '--tag-color': tag.color }"
          :disabled="readonly"
          @click="toggleTag(tag.id)"
        >
          {{ tag.name }}
        </button>
      </div>
      <p v-else class="diary-editor__empty-tags">
        暂无标签，
        <RouterLink to="/settings">前往设置添加</RouterLink>
      </p>
    </footer>
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

.diary-editor__footer {
  margin-top: 1rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--color-border);
}

.diary-editor__empty-tags {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

.diary-editor__empty-tags a {
  color: var(--color-accent);
}

.diary-editor__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.diary-editor__tag {
  border: 1px solid var(--color-border);
  border-radius: 999px;
  padding: 0.25rem 0.75rem;
  font-size: 0.75rem;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition:
    background-color var(--motion-duration) var(--motion-ease),
    color var(--motion-duration) var(--motion-ease),
    border-color var(--motion-duration) var(--motion-ease);
}

.diary-editor__tag.is-selected {
  border-color: color-mix(in srgb, var(--tag-color, var(--color-accent)) 55%, var(--color-border));
  background: color-mix(in srgb, var(--tag-color, var(--color-accent)) 18%, transparent);
  color: var(--color-text-primary);
}

.diary-editor__tag:disabled {
  cursor: default;
}
</style>
