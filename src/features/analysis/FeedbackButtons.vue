<script setup lang="ts">
import { onUnmounted, ref } from 'vue'
import { PhThumbsDown, PhThumbsUp } from '@phosphor-icons/vue'

import { submitFeedback, type FeedbackType } from '@/shared/api/feedback'

const props = withDefaults(
  defineProps<{
    analysisId: number
    responseStyle?: string
  }>(),
  {
    responseStyle: 'empathetic',
  },
)

const emit = defineEmits<{
  submitted: [type: FeedbackType]
}>()

const REASONS = [
  { value: 'too_long', label: '太长' },
  { value: 'too_short', label: '太短' },
  { value: 'irrelevant', label: '不相关' },
  { value: 'too_generic', label: '太笼统' },
  { value: 'lacks_suggestion', label: '缺乏建议' },
] as const

const loading = ref(false)
const submitted = ref(false)
const showReasons = ref(false)
const selectedType = ref<FeedbackType | null>(null)

let hideTimer: ReturnType<typeof setTimeout> | null = null

function scheduleHideConfirmation() {
  if (hideTimer) clearTimeout(hideTimer)
  hideTimer = setTimeout(() => {
    submitted.value = false
    selectedType.value = null
  }, 2500)
}

// Clear pending timer on unmount to prevent ref writes after destroy
onUnmounted(() => {
  if (hideTimer) {
    clearTimeout(hideTimer)
    hideTimer = null
  }
})

async function sendFeedback(type: FeedbackType, reason?: string) {
  loading.value = true
  try {
    await submitFeedback(props.analysisId, {
      feedback_type: type,
      reason,
      response_style: props.responseStyle,
    })
    submitted.value = true
    selectedType.value = type
    showReasons.value = false
    emit('submitted', type)
    scheduleHideConfirmation()
  } catch {
    // 静默失败，不阻塞阅读体验
  } finally {
    loading.value = false
  }
}

async function onPositive() {
  await sendFeedback('positive')
}

function onNegative() {
  selectedType.value = 'negative'
  showReasons.value = true
}

async function onReason(reason: string) {
  await sendFeedback('negative', reason)
}
</script>

<template>
  <div class="feedback-buttons">
    <Transition name="fade">
      <span v-if="submitted" class="feedback-buttons__done">已收到你的反馈</span>
    </Transition>

    <template v-if="!submitted">
      <button
        type="button"
        class="feedback-buttons__btn feedback-buttons__btn--positive"
        :class="{ 'is-selected': selectedType === 'positive' }"
        :disabled="loading"
        title="有帮助"
        @click="onPositive"
      >
        <PhThumbsUp :size="18" weight="duotone" />
      </button>
      <button
        type="button"
        class="feedback-buttons__btn feedback-buttons__btn--negative"
        :class="{ 'is-selected': selectedType === 'negative' && showReasons }"
        :disabled="loading"
        title="需改进"
        @click="onNegative"
      >
        <PhThumbsDown :size="18" weight="duotone" />
      </button>
    </template>

    <Transition name="slide">
      <div v-if="showReasons && !submitted" class="feedback-buttons__reasons">
        <button
          v-for="reason in REASONS"
          :key="reason.value"
          type="button"
          class="feedback-buttons__reason"
          :disabled="loading"
          @click="onReason(reason.value)"
        >
          {{ reason.label }}
        </button>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.feedback-buttons {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.feedback-buttons__done {
  font-size: 0.8125rem;
  color: var(--color-accent);
  font-weight: 500;
}

.feedback-buttons__btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.25rem;
  height: 2.25rem;
  border-radius: 0.625rem;
  border: 1px solid var(--color-border);
  background: var(--color-surface-raised);
  color: var(--color-text-secondary);
  transition:
    transform 0.2s ease,
    background 0.2s ease,
    border-color 0.2s ease;
}

.feedback-buttons__btn:hover:not(:disabled) {
  transform: scale(1.08);
}

.feedback-buttons__btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.feedback-buttons__btn--positive.is-selected,
.feedback-buttons__btn--positive:hover:not(:disabled) {
  border-color: color-mix(in srgb, var(--color-accent) 50%, transparent);
  color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 12%, var(--color-surface-raised));
}

.feedback-buttons__btn--negative.is-selected,
.feedback-buttons__btn--negative:hover:not(:disabled) {
  border-color: color-mix(in srgb, #c45c5c 45%, transparent);
  color: #c45c5c;
  background: color-mix(in srgb, #c45c5c 10%, var(--color-surface-raised));
}

.feedback-buttons__reasons {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  margin-left: 0.25rem;
}

.feedback-buttons__reason {
  padding: 0.25rem 0.625rem;
  font-size: 0.75rem;
  border-radius: 999px;
  border: 1px solid var(--color-border);
  background: var(--color-surface-raised);
  color: var(--color-text-secondary);
  transition:
    background 0.2s ease,
    border-color 0.2s ease;
}

.feedback-buttons__reason:hover:not(:disabled) {
  border-color: color-mix(in srgb, #c45c5c 40%, transparent);
  color: #c45c5c;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.25s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.slide-enter-active,
.slide-leave-active {
  transition:
    opacity 0.25s ease,
    transform 0.25s ease;
}

.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  transform: translateX(-6px);
}
</style>
