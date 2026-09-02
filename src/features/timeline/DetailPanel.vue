<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { PhXCircle } from '@phosphor-icons/vue'

import CardTypeBadge from '@/features/card/CardTypeBadge.vue'
import EmotionChips from '@/features/card/EmotionChips.vue'
import GameButton from '@/shared/components/GameButton.vue'
import GlassPanel from '@/shared/components/GlassPanel.vue'
import { timelineCopy as copy } from '@/shared/copy/timeline'
import { useTimelineStore } from '@/stores/timeline'
import { useDiaryStore } from '@/stores/diary'
import { useCardStore } from '@/stores/card'
import { formatApiError } from '@/shared/utils/apiError'
import { findCardForDiary } from '@/shared/utils/cardFormat'
import { diaryEntrySummary } from '@/shared/utils/diaryFormat'
import { serverDateIso } from '@/shared/utils/timeFormat'

const router = useRouter()
const timeline = useTimelineStore()
const diaryStore = useDiaryStore()
const cardStore = useCardStore()

const showDeleteConfirm = ref(false)
const deleteError = ref<string | null>(null)

const entry = computed(() => timeline.selectedEntry)

const linkedCard = computed(() =>
  entry.value ? findCardForDiary(cardStore.cards, entry.value.id) : null,
)

watch(
  entry,
  () => {
    showDeleteConfirm.value = false
    deleteError.value = null
  },
  { immediate: true },
)

function close() {
  timeline.selectEntry(null)
}

function continueWriting() {
  if (!entry.value) return
  router.push(`/write/${entry.value.id}`)
}

function exportMarkdown() {
  if (!entry.value) return
  const e = entry.value
  const date = e.date || '未知日期'
  const weather = e.weather ? `  \n*天气：${e.weather}*` : ''
  const md = `# ${date}\n${weather}\n\n## 日记\n\n${e.content}\n`
  const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `nightdiary-${date}.md`
  a.click()
  URL.revokeObjectURL(url)
}

async function executeDelete() {
  if (!entry.value) return
  showDeleteConfirm.value = false
  deleteError.value = null
  const id = entry.value.id
  try {
    await diaryStore.removeEntry(id)
    timeline.selectEntry(null)
    await timeline.load()
  } catch (err) {
    deleteError.value = formatApiError(err, '删除日记失败')
  }
}
</script>

<template>
  <GlassPanel v-if="entry" class="detail-panel" elevated>
    <button type="button" class="detail-panel__close" title="关闭" @click="close">
      <PhXCircle :size="16" />
    </button>

    <p class="detail-panel__date">{{ entry.date ?? serverDateIso(entry.created_at) }}</p>
    <p v-if="entry.weather" class="detail-panel__weather">{{ entry.weather }}</p>

    <div v-if="linkedCard" class="detail-panel__card-origin">
      <EmotionChips :emotions="linkedCard.emotions" :emotion="linkedCard.emotion" :size="12" />
      <CardTypeBadge :card-type="linkedCard.card_type" />
    </div>

    <p class="detail-panel__summary font-diary">
      {{ diaryEntrySummary(entry, cardStore.cards, 120) }}
    </p>

    <div class="detail-panel__actions">
      <GameButton variant="primary" @click="continueWriting">{{ copy.detailContinue }}</GameButton>
      <GameButton variant="ghost" @click="exportMarkdown">{{ copy.detailExport }}</GameButton>
      <GameButton variant="ghost" class="detail-panel__delete" @click="showDeleteConfirm = true">
        {{ copy.detailDelete }}
      </GameButton>
    </div>

    <p v-if="deleteError" class="detail-panel__error">{{ deleteError }}</p>

    <div v-if="showDeleteConfirm" class="detail-panel__confirm">
      <p class="detail-panel__confirm-title">{{ copy.detailDeleteConfirm }}</p>
      <p class="detail-panel__confirm-desc">{{ copy.detailDeleteConfirmDesc }}</p>
      <div class="detail-panel__confirm-actions">
        <GameButton variant="ghost" @click="showDeleteConfirm = false">
          {{ copy.detailDeleteCancel }}
        </GameButton>
        <GameButton variant="primary" @click="executeDelete">{{ copy.detailDeleteConfirmBtn }}</GameButton>
      </div>
    </div>
  </GlassPanel>
</template>

<style scoped>
.detail-panel {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
  padding: 1.25rem;
}
.detail-panel__close {
  position: absolute;
  top: 0.75rem;
  right: 0.75rem;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  padding: 0.25rem;
}
.detail-panel__close:hover {
  color: var(--color-text-primary);
}
.detail-panel__date {
  margin: 0;
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text-primary);
}
.detail-panel__weather {
  margin: 0;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}
.detail-panel__card-origin {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.detail-panel__summary {
  margin: 0;
  font-size: 0.875rem;
  line-height: 1.7;
  color: var(--color-text-primary);
}
.detail-panel__actions {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  margin-top: 0.5rem;
}
.detail-panel__delete {
  color: var(--color-danger);
}
.detail-panel__error {
  margin: 0;
  font-size: 0.75rem;
  color: var(--color-danger);
}
.detail-panel__confirm {
  border-top: 1px solid var(--color-border);
  padding-top: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.detail-panel__confirm-title {
  margin: 0;
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-text-primary);
}
.detail-panel__confirm-desc {
  margin: 0;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}
.detail-panel__confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}
</style>
