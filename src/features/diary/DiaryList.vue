<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import type { DiaryEntry } from '@/shared/api/diary'
import { listDiaryEntries } from '@/shared/api/diary'
import { diaryStatus, diaryStatusLabel, diarySummary } from '@/shared/utils/diaryFormat'

const props = withDefaults(
  defineProps<{
    pageSize?: number
  }>(),
  {
    pageSize: 20,
  },
)

const router = useRouter()
const entries = ref<DiaryEntry[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const skip = ref(0)
const hasMore = ref(true)

async function refresh() {
  skip.value = 0
  hasMore.value = true
  await loadMore(true)
}

async function loadMore(reset = false) {
  if (loading.value) return
  if (!reset && !hasMore.value) return

  loading.value = true
  error.value = null
  try {
    const nextSkip = reset ? 0 : skip.value
    const batch = await listDiaryEntries({ skip: nextSkip, limit: props.pageSize })
    if (reset) {
      entries.value = batch
    } else {
      entries.value = [...entries.value, ...batch]
    }
    skip.value = nextSkip + batch.length
    hasMore.value = batch.length === props.pageSize
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载列表失败'
  } finally {
    loading.value = false
  }
}

function openEntry(entry: DiaryEntry) {
  router.push(`/write/${entry.id}`)
}

onMounted(() => {
  void refresh()
})

defineExpose({ refresh, entries })
</script>

<template>
  <div class="diary-list">
    <p v-if="error" class="diary-list__error">{{ error }}</p>
    <p v-else-if="loading && entries.length === 0" class="diary-list__hint">加载中…</p>
    <p v-else-if="entries.length === 0" class="diary-list__hint">还没有日记</p>

    <ul v-else class="diary-list__items">
      <li v-for="entry in entries" :key="entry.id">
        <button type="button" class="diary-list__item" @click="openEntry(entry)">
          <span class="diary-list__summary">{{ diarySummary(entry.content) }}</span>
          <span class="diary-list__meta">
            <span class="diary-list__chip">{{ diaryStatusLabel(diaryStatus(entry)) }}</span>
            <span v-if="entry.date">{{ entry.date }}</span>
          </span>
        </button>
      </li>
    </ul>

    <button
      v-if="hasMore && entries.length > 0"
      type="button"
      class="diary-list__more"
      :disabled="loading"
      @click="loadMore(false)"
    >
      {{ loading ? '加载中…' : '加载更多' }}
    </button>
  </div>
</template>

<style scoped>
.diary-list__hint,
.diary-list__error {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
}

.diary-list__error {
  color: var(--color-danger);
}

.diary-list__items {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  gap: 0.5rem;
}

.diary-list__item {
  width: 100%;
  text-align: left;
  border: 1px solid var(--color-border);
  border-radius: 0.625rem;
  background: var(--color-bg-elevated);
  padding: 0.625rem 0.75rem;
  cursor: pointer;
  transition: background-color var(--motion-duration) var(--motion-ease);
}

.diary-list__item:hover {
  background: var(--color-bg-elevated-2);
}

.diary-list__summary {
  display: block;
  font-size: 0.8125rem;
  color: var(--color-text-primary);
}

.diary-list__meta {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.375rem;
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
}

.diary-list__chip {
  border-radius: 999px;
  padding: 0.125rem 0.5rem;
  background: color-mix(in srgb, var(--color-accent) 12%, transparent);
  color: var(--color-accent-muted);
}

.diary-list__more {
  margin-top: 0.75rem;
  width: 100%;
  border: 1px dashed var(--color-border);
  border-radius: 0.5rem;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 0.75rem;
  padding: 0.375rem;
  cursor: pointer;
}
</style>
