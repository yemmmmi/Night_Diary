<script setup lang="ts">
import { computed, ref } from 'vue'

import AIAnalysisPanel from '@/features/analysis/AIAnalysisPanel.vue'
import GameButton from '@/shared/components/GameButton.vue'
import GlassPanel from '@/shared/components/GlassPanel.vue'
import type { AnalysisRecord } from '@/shared/api/analysis'
import type { DiaryEntry } from '@/shared/api/diary'
import { diarySceneCopy as copy } from '@/shared/copy/diaryScene'
import { useAnalysisStore } from '@/stores/analysis'
import { useSettingsStore } from '@/stores/settings'
import { diaryStatus } from '@/shared/utils/diaryFormat'

const props = defineProps<{
  diaryId: number
  entry: DiaryEntry
  analysis: AnalysisRecord | null
  loading?: boolean
  triggering?: boolean
}>()

const emit = defineEmits<{
  refreshed: []
}>()

const analysisStore = useAnalysisStore()
const settings = useSettingsStore()

const showDeleteConfirm = ref(false)

const hasAiReply = computed(() =>
  Boolean(props.analysis?.reply?.trim() || props.entry.reply?.trim()),
)

const showTriggerButton = computed(
  () =>
    !hasAiReply.value &&
    !props.loading &&
    !props.triggering &&
    diaryStatus(props.entry) !== 'draft',
)

const showManageActions = computed(
  () => hasAiReply.value && !props.triggering && !props.loading,
)

async function onTrigger() {
  await analysisStore.triggerForDiary(props.diaryId)
  emit('refreshed')
}

async function onRegenerate() {
  await analysisStore.regenerateForDiary(props.diaryId)
  emit('refreshed')
}

async function onDeleteConfirm() {
  showDeleteConfirm.value = false
  await analysisStore.removeForDiary(props.diaryId)
  emit('refreshed')
}
</script>

<template>
  <section id="reply" class="diary-reply">
    <h2 class="diary-reply__title">
      {{ settings.replierName ? `${settings.replierName}的${copy.replySectionTitle}` : copy.replySectionTitle }}
    </h2>

    <p v-if="analysisStore.error" class="diary-reply__error">{{ analysisStore.error }}</p>

    <AIAnalysisPanel
      :entry="entry"
      :analysis="analysis"
      :loading="loading"
      :triggering="triggering"
      hide-diary-preview
    >
      <template #actions>
        <div v-if="showTriggerButton" class="diary-reply__actions">
          <GameButton
            variant="primary"
            class="glow-pulse"
            :disabled="triggering"
            @click="onTrigger"
          >
            {{ triggering ? '分析中…' : '获取回信' }}
          </GameButton>
          <p class="diary-reply__hint">会认真读你的日记，给你回信</p>
        </div>

        <div v-if="showManageActions" class="diary-reply__actions diary-reply__actions--row">
          <GameButton
            variant="secondary"
            :disabled="triggering || analysisStore.deleting"
            @click="onRegenerate"
          >
            {{ triggering ? '重新生成中…' : '重新生成回信' }}
          </GameButton>
          <GameButton
            variant="ghost"
            :disabled="triggering || analysisStore.deleting"
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
        <GlassPanel elevated class="confirm-dialog">
          <p class="confirm-dialog__title">确定删除这封回信吗？</p>
          <p class="confirm-dialog__desc">删除后可重新获取回信，日记内容不受影响</p>
          <div class="confirm-dialog__actions">
            <GameButton variant="secondary" @click="showDeleteConfirm = false">取消</GameButton>
            <GameButton variant="primary" @click="onDeleteConfirm">确认删除</GameButton>
          </div>
        </GlassPanel>
      </div>
    </Teleport>
  </section>
</template>

<style scoped>
.diary-reply {
  margin-top: 1.5rem;
  padding-top: 1.25rem;
  border-top: 1px solid var(--color-border);
}

.diary-reply__title {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-text-secondary);
  margin-bottom: 0.875rem;
  letter-spacing: 0.02em;
}

.diary-reply__error {
  margin-bottom: 0.75rem;
  padding: 0.625rem 0.75rem;
  border-radius: 0.5rem;
  font-size: 0.8125rem;
  color: var(--color-danger);
  background: color-mix(in srgb, var(--color-danger) 10%, transparent);
}

.diary-reply__actions {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

.diary-reply__actions--row {
  flex-direction: row;
  justify-content: center;
  flex-wrap: wrap;
}

.diary-reply__hint {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
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
