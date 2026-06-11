<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PhArrowLeft } from '@phosphor-icons/vue'

import AIAnalysisPanel from '@/features/analysis/AIAnalysisPanel.vue'
import GameButton from '@/shared/components/GameButton.vue'
import { useAnalysisStore } from '@/stores/analysis'
import { useDiaryStore } from '@/stores/diary'

const route = useRoute()
const router = useRouter()
const diaryStore = useDiaryStore()
const analysisStore = useAnalysisStore()

const loadError = ref<string | null>(null)
const showDeleteConfirm = ref(false)

const diaryId = computed(() => {
  const raw = route.params.diaryId
  const parsed = Number(raw)
  return Number.isFinite(parsed) ? parsed : null
})

const entry = computed(() => diaryStore.currentEntry)

const hasAiReply = computed(() =>
  Boolean(
    analysisStore.current?.ai_ans?.trim() ||
      entry.value?.ai_ans?.trim(),
  ),
)

const showTriggerButton = computed(
  () =>
    !hasAiReply.value &&
    !analysisStore.loading &&
    !analysisStore.triggering,
)

const showManageActions = computed(
  () => hasAiReply.value && !analysisStore.triggering && !analysisStore.loading,
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

async function onRegenerate() {
  if (!diaryId.value) return
  try {
    await analysisStore.regenerateForDiary(diaryId.value)
    await diaryStore.fetchEntry(diaryId.value)
  } catch {
    // error surfaced via analysisStore.error
  }
}

async function onDeleteConfirm() {
  if (!diaryId.value) return
  showDeleteConfirm.value = false
  try {
    await analysisStore.removeForDiary(diaryId.value)
    await diaryStore.fetchEntry(diaryId.value)
  } catch {
    // error surfaced via analysisStore.error
  }
}

function goBack() {
  router.push('/')
}

function goEdit() {
  if (!diaryId.value) return
  router.push(`/write/${diaryId.value}`)
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
      <GameButton v-if="diaryId" variant="ghost" @click="goEdit">编辑日记</GameButton>
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

        <div v-if="showManageActions" class="analysis-scene__actions analysis-scene__actions--row">
          <GameButton
            variant="secondary"
            :disabled="analysisStore.triggering || analysisStore.deleting"
            @click="onRegenerate"
          >
            {{ analysisStore.triggering ? '重新生成中…' : '重新生成回信' }}
          </GameButton>
          <GameButton
            variant="ghost"
            :disabled="analysisStore.triggering || analysisStore.deleting"
            @click="showDeleteConfirm = true"
          >
            删除回信
          </GameButton>
        </div>
      </template>
    </AIAnalysisPanel>

    <Teleport to="body">
      <div
        v-if="showDeleteConfirm"
        class="confirm-overlay"
        @click.self="showDeleteConfirm = false"
      >
        <div class="confirm-dialog">
          <p class="confirm-dialog__title">确定删除这封 AI 回信吗？</p>
          <p class="confirm-dialog__desc">删除后可重新获取回信，日记内容不受影响</p>
          <div class="confirm-dialog__actions">
            <GameButton variant="secondary" @click="showDeleteConfirm = false">取消</GameButton>
            <GameButton variant="primary" @click="onDeleteConfirm">确认删除</GameButton>
          </div>
        </div>
      </div>
    </Teleport>
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

.analysis-scene__actions--row {
  flex-direction: row;
  justify-content: center;
  flex-wrap: wrap;
}

.analysis-scene__hint {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  text-align: center;
}

.confirm-overlay {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.35);
  backdrop-filter: blur(4px);
}

.confirm-dialog {
  width: min(20rem, calc(100vw - 2rem));
  padding: 1.5rem;
  border-radius: var(--radius-outer);
  border: 1px solid var(--color-border);
  background: var(--color-bg-elevated);
  text-align: center;
}

.confirm-dialog__title {
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 0.375rem;
}

.confirm-dialog__desc {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  margin-bottom: 1rem;
}

.confirm-dialog__actions {
  display: flex;
  justify-content: center;
  gap: 0.75rem;
}
</style>
