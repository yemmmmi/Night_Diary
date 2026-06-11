<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PhArrowLeft } from '@phosphor-icons/vue'

import AIAnalysisPanel from '@/features/analysis/AIAnalysisPanel.vue'
import GameButton from '@/shared/components/GameButton.vue'
import { useAnalysisStore } from '@/stores/analysis'
import { useDiaryStore } from '@/stores/diary'
import { diaryStatus } from '@/shared/utils/diaryFormat'

const route = useRoute()
const router = useRouter()
const diaryStore = useDiaryStore()
const analysisStore = useAnalysisStore()

const loadError = ref<string | null>(null)

const diaryId = computed(() => {
  const raw = route.params.diaryId
  const parsed = Number(raw)
  return Number.isFinite(parsed) ? parsed : null
})

const entry = computed(() => diaryStore.currentEntry)

const canTrigger = computed(() => {
  if (!entry.value) return false
  const status = diaryStatus(entry.value)
  return status === 'pending' || status === 'reply'
})

const showTriggerButton = computed(
  () =>
    canTrigger.value &&
    !analysisStore.current &&
    !analysisStore.loading &&
    !entry.value?.ai_ans?.trim(),
)

async function loadPage() {
  loadError.value = null
  analysisStore.clear()
  if (!diaryId.value) {
    loadError.value = '无效的日记 ID'
    return
  }

  try {
    await diaryStore.fetchEntry(diaryId.value)
    await analysisStore.loadForDiary(diaryId.value)
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : '加载失败'
  }
}

async function onTrigger() {
  if (!diaryId.value) return
  try {
    await analysisStore.triggerForDiary(diaryId.value)
    await diaryStore.fetchEntry(diaryId.value)
  } catch {
    // error surfaced via analysisStore.error
  }
}

function goBack() {
  router.push('/')
}

onMounted(() => {
  void loadPage()
})

watch(
  () => route.params.diaryId,
  () => {
    void loadPage()
  },
)
</script>

<template>
  <main class="analysis-scene">
    <header class="analysis-scene__header">
      <GameButton variant="ghost" @click="goBack">
        <PhArrowLeft :size="16" />
        返回
      </GameButton>
      <h1 class="analysis-scene__title">AI 回信</h1>
      <span class="analysis-scene__spacer" />
    </header>

    <p v-if="loadError" class="analysis-scene__error">{{ loadError }}</p>
    <p v-else-if="analysisStore.error" class="analysis-scene__error">{{ analysisStore.error }}</p>

    <AIAnalysisPanel
      v-if="entry && !loadError"
      :entry="entry"
      :analysis="analysisStore.current"
      :loading="analysisStore.loading"
      :triggering="analysisStore.triggering"
    >
      <template #actions>
        <div v-if="showTriggerButton" class="analysis-scene__actions">
          <GameButton
            variant="primary"
            class="glow-pulse"
            :disabled="analysisStore.triggering"
            @click="onTrigger"
          >
            {{ analysisStore.triggering ? '分析中…' : '获取 AI 回信' }}
          </GameButton>
          <p class="analysis-scene__hint">夜记会认真阅读你的日记，并写一封回信给你</p>
        </div>
      </template>
    </AIAnalysisPanel>
  </main>
</template>

<style scoped>
.analysis-scene {
  min-height: calc(100vh - 2.5rem);
  max-width: 42rem;
  margin: 0 auto;
  padding: 1.25rem 1rem 2rem;
}

.analysis-scene__header {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1.25rem;
}

.analysis-scene__title {
  text-align: center;
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.analysis-scene__spacer {
  width: 4.5rem;
}

.analysis-scene__error {
  padding: 0.75rem 1rem;
  border-radius: 0.625rem;
  background: color-mix(in srgb, #c45c5c 12%, transparent);
  color: #c45c5c;
  font-size: 0.875rem;
  margin-bottom: 1rem;
}

.analysis-scene__actions {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.625rem;
  margin-top: 0.5rem;
}

.analysis-scene__hint {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  text-align: center;
}
</style>
