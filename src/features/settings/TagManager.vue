<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import GameButton from '@/shared/components/GameButton.vue'
import { DEFAULT_MOOD_TAGS } from '@/shared/constants/moodTags'
import { createTag, deleteTag, listTags, seedMoodTags, type Tag } from '@/shared/api/tags'
import { formatApiError } from '@/shared/utils/apiError'

const PRESET_COLORS = ['#6B7280', '#EF4444', '#F59E0B', '#10B981', '#3B82F6', '#8B5CF6'] as const

const tags = ref<Tag[]>([])
const loading = ref(true)
const saving = ref(false)
const seeding = ref(false)
const error = ref<string | null>(null)

const form = reactive({
  name: '',
  color: PRESET_COLORS[0] as string,
})

const existingNames = () => new Set(tags.value.map((tag) => tag.name))

async function refresh() {
  loading.value = true
  error.value = null
  try {
    tags.value = await listTags()
  } catch (err) {
    error.value = formatApiError(err, '加载标签失败')
  } finally {
    loading.value = false
  }
}

async function ensureMoodTags() {
  seeding.value = true
  error.value = null
  try {
    tags.value = await seedMoodTags()
  } catch (err) {
    error.value = formatApiError(err, '添加常用标签失败')
  } finally {
    seeding.value = false
  }
}

async function addPreset(name: string, color: string) {
  if (existingNames().has(name)) return
  saving.value = true
  error.value = null
  try {
    await createTag({ name, color })
    await refresh()
  } catch (err) {
    error.value = formatApiError(err, `添加「${name}」失败`)
  } finally {
    saving.value = false
  }
}

async function submit() {
  const name = form.name.trim()
  if (!name) return

  saving.value = true
  error.value = null
  try {
    await createTag({ name, color: form.color })
    form.name = ''
    await refresh()
  } catch (err) {
    error.value = formatApiError(err, '创建标签失败')
  } finally {
    saving.value = false
  }
}

async function remove(tag: Tag) {
  if (!window.confirm(`确定删除标签「${tag.name}」吗？`)) return
  error.value = null
  try {
    await deleteTag(tag.id)
    await refresh()
  } catch (err) {
    error.value = formatApiError(err, '删除标签失败')
  }
}

onMounted(async () => {
  await refresh()
  if (tags.value.length === 0) {
    await ensureMoodTags()
  }
})

defineExpose({ refresh })
</script>

<template>
  <div class="tag-manager">
    <div class="tag-manager__presets">
      <p class="tag-manager__presets-title">常用心情标签</p>
      <p class="tag-manager__presets-hint">点击文字即可添加；写日记时会显示完整标签名。</p>
      <div class="tag-manager__preset-list">
        <button
          v-for="preset in DEFAULT_MOOD_TAGS"
          :key="preset.name"
          type="button"
          class="tag-manager__preset"
          :class="{ 'is-added': existingNames().has(preset.name) }"
          :style="{ '--tag-color': preset.color }"
          :disabled="saving || seeding || existingNames().has(preset.name)"
          @click="addPreset(preset.name, preset.color)"
        >
          <span class="tag-manager__preset-dot" />
          {{ preset.name }}
        </button>
      </div>
      <GameButton variant="ghost" :disabled="seeding" @click="ensureMoodTags">
        {{ seeding ? '添加中…' : '一键补全常用标签' }}
      </GameButton>
    </div>

    <form class="tag-manager__form" @submit.prevent="submit">
      <input
        v-model="form.name"
        class="tag-manager__input"
        maxlength="32"
        placeholder="自定义标签，如「期待」"
        required
      />
      <div class="tag-manager__colors">
        <button
          v-for="color in PRESET_COLORS"
          :key="color"
          type="button"
          class="tag-manager__color"
          :class="{ 'is-selected': form.color === color }"
          :style="{ backgroundColor: color }"
          :title="color"
          @click="form.color = color"
        />
      </div>
      <GameButton type="submit" variant="secondary" :disabled="saving">
        {{ saving ? '添加中…' : '添加自定义标签' }}
      </GameButton>
    </form>

    <p v-if="error" class="tag-manager__error">{{ error }}</p>
    <p v-else-if="loading" class="tag-manager__hint">加载中…</p>
    <ul v-else class="tag-manager__list">
      <li v-for="tag in tags" :key="tag.id" class="tag-manager__item">
        <span class="tag-manager__pill" :style="{ '--tag-color': tag.color }">
          <span class="tag-manager__pill-dot" />
          {{ tag.name }}
        </span>
        <span v-if="tag.usage_count != null" class="tag-manager__usage">已用 {{ tag.usage_count }} 次</span>
        <GameButton variant="ghost" class="tag-manager__delete" @click="remove(tag)">删除</GameButton>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.tag-manager {
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
}

.tag-manager__presets {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid var(--color-border);
}

.tag-manager__presets-title {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.tag-manager__presets-hint {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

.tag-manager__preset-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.tag-manager__preset {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.375rem 0.75rem;
  border-radius: 999px;
  border: 1px solid color-mix(in srgb, var(--tag-color, var(--color-accent)) 45%, var(--color-border));
  background: color-mix(in srgb, var(--tag-color, var(--color-accent)) 12%, transparent);
  color: var(--color-text-primary);
  font-size: 0.8125rem;
  cursor: pointer;
}

.tag-manager__preset.is-added,
.tag-manager__preset:disabled {
  opacity: 0.55;
  cursor: default;
}

.tag-manager__preset-dot,
.tag-manager__pill-dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  background: var(--tag-color, var(--color-accent));
  flex-shrink: 0;
}

.tag-manager__form {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.625rem;
}

.tag-manager__input {
  flex: 1;
  min-width: 8rem;
  padding: 0.625rem 0.75rem;
  border-radius: 0.625rem;
  border: 1px solid var(--color-border);
  background: var(--color-bg-elevated-2);
  color: var(--color-text-primary);
  font-size: 0.875rem;
}

.tag-manager__colors {
  display: flex;
  gap: 0.375rem;
}

.tag-manager__color {
  width: 1.25rem;
  height: 1.25rem;
  border-radius: 50%;
  border: 2px solid transparent;
  cursor: pointer;
}

.tag-manager__color.is-selected {
  border-color: var(--color-text-primary);
  box-shadow: 0 0 0 2px var(--color-bg-elevated);
}

.tag-manager__list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.tag-manager__item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.tag-manager__pill {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.25rem 0.75rem;
  border-radius: 999px;
  font-size: 0.8125rem;
  border: 1px solid color-mix(in srgb, var(--tag-color, var(--color-accent)) 55%, var(--color-border));
  background: color-mix(in srgb, var(--tag-color, var(--color-accent)) 18%, transparent);
  color: var(--color-text-primary);
}

.tag-manager__usage {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  flex: 1;
}

.tag-manager__delete {
  font-size: 0.8125rem;
  color: var(--color-danger) !important;
}

.tag-manager__hint,
.tag-manager__error {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
}

.tag-manager__error {
  color: var(--color-danger);
}
</style>
