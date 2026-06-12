<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import GameButton from '@/shared/components/GameButton.vue'
import { createTag, deleteTag, listTags, type Tag } from '@/shared/api/tags'
import { formatApiError } from '@/shared/utils/apiError'

const PRESET_COLORS = ['#6B7280', '#EF4444', '#F59E0B', '#10B981', '#3B82F6', '#8B5CF6'] as const

const tags = ref<Tag[]>([])
const loading = ref(true)
const saving = ref(false)
const error = ref<string | null>(null)

const form = reactive({
  name: '',
  color: PRESET_COLORS[0] as string,
})

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

onMounted(() => {
  void refresh()
})

defineExpose({ refresh })
</script>

<template>
  <div class="tag-manager">
    <form class="tag-manager__form" @submit.prevent="submit">
      <input
        v-model="form.name"
        class="tag-manager__input"
        maxlength="32"
        placeholder="新标签名称"
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
        {{ saving ? '添加中…' : '添加标签' }}
      </GameButton>
    </form>

    <p v-if="error" class="tag-manager__error">{{ error }}</p>
    <p v-else-if="loading" class="tag-manager__hint">加载中…</p>
    <p v-else-if="tags.length === 0" class="tag-manager__hint">暂无标签，添加后可在写日记时选用。</p>
    <ul v-else class="tag-manager__list">
      <li v-for="tag in tags" :key="tag.id" class="tag-manager__item">
        <span class="tag-manager__pill" :style="{ '--tag-color': tag.color }">{{ tag.name }}</span>
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
  display: inline-block;
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
