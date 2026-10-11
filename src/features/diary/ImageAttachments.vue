<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { PhImage, PhX } from '@phosphor-icons/vue'

import {
  ACCEPTED_IMAGE_TYPES,
  MAX_IMAGE_BYTES,
  fetchImageObjectUrl,
  uploadImage,
} from '@/shared/api/uploads'
import { diarySceneCopy as copy } from '@/shared/copy/diaryScene'

const props = withDefaults(
  defineProps<{
    modelValue: number[]
    readonly?: boolean
  }>(),
  { readonly: false },
)

const emit = defineEmits<{ 'update:modelValue': [value: number[]] }>()

const uploading = ref(false)
const error = ref<string | null>(null)
const thumbs = ref<Record<number, string>>({})
const fileInput = ref<HTMLInputElement | null>(null)

async function loadThumb(id: number) {
  if (thumbs.value[id]) return
  try {
    thumbs.value[id] = await fetchImageObjectUrl(id)
  } catch {
    // Preview failure is non-fatal: the attachment id is still preserved.
  }
}

watch(
  () => props.modelValue,
  (ids) => {
    ids.forEach((id) => void loadThumb(id))
  },
  { immediate: true },
)

function revoke(id: number) {
  const url = thumbs.value[id]
  if (!url) return
  URL.revokeObjectURL(url)
  delete thumbs.value[id]
}

function remove(id: number) {
  revoke(id)
  emit(
    'update:modelValue',
    props.modelValue.filter((value) => value !== id),
  )
}

function pick() {
  error.value = null
  fileInput.value?.click()
}

async function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  input.value = ''
  if (files.length === 0) return

  uploading.value = true
  error.value = null
  const added: number[] = []
  try {
    for (const file of files) {
      if (file.size > MAX_IMAGE_BYTES) {
        error.value = copy.imageTooLarge
        continue
      }
      const asset = await uploadImage(file)
      added.push(asset.id)
      await loadThumb(asset.id)
    }
    if (added.length > 0) {
      emit('update:modelValue', [...props.modelValue, ...added])
    }
  } catch {
    error.value = copy.attachFailed
  } finally {
    uploading.value = false
  }
}

onUnmounted(() => {
  Object.keys(thumbs.value).forEach((key) => revoke(Number(key)))
})
</script>

<template>
  <div class="image-attachments">
    <ul v-if="modelValue.length" class="image-attachments__list">
      <li
        v-for="id in modelValue"
        :key="id"
        class="image-attachments__item"
        data-testid="image-attachment"
      >
        <img
          v-if="thumbs[id]"
          :src="thumbs[id]"
          :alt="copy.attachImage"
          class="image-attachments__thumb"
        />
        <span v-else class="image-attachments__placeholder" />
        <button
          v-if="!readonly"
          type="button"
          class="image-attachments__remove"
          :title="copy.removeImage"
          :aria-label="copy.removeImage"
          data-testid="image-remove"
          @click="remove(id)"
        >
          <PhX :size="12" />
        </button>
      </li>
    </ul>

    <button
      v-if="!readonly"
      type="button"
      class="image-attachments__add"
      :disabled="uploading"
      data-testid="image-add"
      @click="pick"
    >
      <PhImage :size="15" />
      <span>{{ uploading ? copy.attaching : copy.attachImage }}</span>
    </button>

    <input
      ref="fileInput"
      type="file"
      class="image-attachments__input"
      :accept="ACCEPTED_IMAGE_TYPES"
      multiple
      @change="onFileChange"
    />

    <p v-if="error" class="image-attachments__error" data-testid="image-error">{{ error }}</p>
  </div>
</template>

<style scoped>
.image-attachments {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.image-attachments__list {
  display: flex;
  gap: 0.375rem;
  list-style: none;
  margin: 0;
  padding: 0;
}

.image-attachments__item {
  position: relative;
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 0.375rem;
  overflow: hidden;
  border: 1px solid var(--color-border);
}

.image-attachments__thumb,
.image-attachments__placeholder {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  background: var(--color-bg-elevated);
}

.image-attachments__remove {
  position: absolute;
  top: 0;
  right: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1rem;
  height: 1rem;
  padding: 0;
  border: none;
  background: color-mix(in srgb, var(--color-danger) 85%, transparent);
  color: #fff;
  cursor: pointer;
}

.image-attachments__add {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  background: none;
  border: none;
  padding: 0;
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  cursor: pointer;
}
.image-attachments__add:hover:not(:disabled) {
  color: var(--color-text-primary);
}
.image-attachments__add:disabled {
  opacity: 0.55;
  cursor: progress;
}

.image-attachments__input {
  display: none;
}

.image-attachments__error {
  font-size: 0.75rem;
  color: var(--color-danger);
  width: 100%;
  margin: 0;
}
</style>