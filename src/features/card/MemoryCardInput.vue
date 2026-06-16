<script setup lang="ts">
/**
 * MemoryCardInput — lightweight emotion+event+tags capture.
 *
 * Three modes:
 *  - quick:   tap an emotion → save instantly  (~5 s)
 *  - standard: emotion + event summary + tags  (~30 s)
 *  - guided:  AI-generated prompt questions    (reserved)
 */
import { computed, onMounted, ref, watch } from 'vue'
import {
  PhCheck,
  PhFloppyDisk,
  PhPlus,
  PhSpinner,
  PhX,
  PhArrowRight,
  PhArrowLeft,
} from '@phosphor-icons/vue'

import { createCard, generateCardPrompt } from '@/shared/api/card'
import type { CardCreatePayload } from '@/shared/api/card'
import { formatApiError } from '@/shared/utils/apiError'
import { cardCopy as copy, PRESET_EMOTIONS, QUICK_TAGS } from '@/shared/copy/card'
import GameButton from '@/shared/components/GameButton.vue'

// ── Props ──────────────────────────────────────────────────────────

const props = withDefaults(
  defineProps<{
    /** Pre-fill emotion for external triggers */
    initialEmotion?: string
    /** Start in quick mode (home screen tap) vs standard (card drawer) */
    mode?: 'quick' | 'standard' | 'guided'
    /** Auto-close after successful save */
    autoClose?: boolean
  }>(),
  {
    initialEmotion: '',
    mode: 'standard',
    autoClose: false,
  },
)

// ── Emits ──────────────────────────────────────────────────────────

const emit = defineEmits<{
  saved: [card: CardCreatePayload & { card_id: string }]
  close: []
}>()

// ── State ──────────────────────────────────────────────────────────

const selectedEmotion = ref('')
const customEmotion = ref('')
const eventSummary = ref('')
const selectedTags = ref<string[]>([])
const saving = ref(false)
const saveError = ref<string | null>(null)
const savedCardId = ref<string | null>(null)
const showCustomInput = ref(false)

// ── Guided mode state ────────────────────────────────────────────
const guidedQuestions = ref<string[]>([])
const currentQuestionIndex = ref(0)
const guidedAnswers = ref<string[]>([])
const guidedLoading = ref(false)
const guidedError = ref<string | null>(null)

// ── Computed ───────────────────────────────────────────────────────

const currentEmotion = computed(() => customEmotion.value || selectedEmotion.value)
const moodScore = computed(() => {
  const preset = PRESET_EMOTIONS.find(e => e.key === selectedEmotion.value)
  return preset ? preset.moodScore : 0.5
})
const canSave = computed(() => selectedEmotion.value.trim().length > 0)
const isQuickMode = computed(() => props.mode === 'quick')
const isGuidedMode = computed(() => props.mode === 'guided')
const currentQuestion = computed(() => guidedQuestions.value[currentQuestionIndex.value] || '')
const isLastQuestion = computed(() => currentQuestionIndex.value >= guidedQuestions.value.length - 1)
const hasMoreQuestions = computed(() => guidedQuestions.value.length > 0)

// ── Watchers ───────────────────────────────────────────────────────

// Pre-fill from prop
watch(
  () => props.initialEmotion,
  (val) => {
    if (val) selectedEmotion.value = val
  },
)

// ── Methods ────────────────────────────────────────────────────────

function selectEmotion(emotion: string) {
  selectedEmotion.value = emotion
  customEmotion.value = ''

  if (isQuickMode.value) {
    // Quick mode: save immediately on emotion tap
    saveCard()
  }
}

function toggleTag(tag: string) {
  const idx = selectedTags.value.indexOf(tag)
  if (idx === -1) {
    selectedTags.value.push(tag)
  } else {
    selectedTags.value.splice(idx, 1)
  }
}

function startCustomEmotion() {
  showCustomInput.value = true
  customEmotion.value = selectedEmotion.value
}

function confirmCustomEmotion() {
  if (customEmotion.value.trim()) {
    selectedEmotion.value = customEmotion.value.trim()
  }
  showCustomInput.value = false
}

function cancelCustomEmotion() {
  showCustomInput.value = false
  customEmotion.value = ''
}

async function saveCard() {
  if (!canSave.value) return

  saving.value = true
  saveError.value = null

  try {
    const payload: CardCreatePayload = {
      emotion: currentEmotion.value,
      event_summary: eventSummary.value || null,
      mood_score: moodScore.value,
      tags: selectedTags.value,
      importance: isQuickMode.value ? 0.6 : 0.7,
      card_type: props.mode,
    }

    const card = await createCard(payload)
    savedCardId.value = card.card_id

    emit('saved', { ...payload, card_id: card.card_id })

    if (props.autoClose) {
      setTimeout(() => emit('close'), 600)
    }
  } catch (err) {
    saveError.value = formatApiError(err, copy.saveError)
  } finally {
    saving.value = false
  }
}

function reset() {
  selectedEmotion.value = ''
  customEmotion.value = ''
  eventSummary.value = ''
  selectedTags.value = []
  saveError.value = null
  savedCardId.value = null
  showCustomInput.value = false
  guidedQuestions.value = []
  currentQuestionIndex.value = 0
  guidedAnswers.value = []
  guidedError.value = null
}

// ── Guided mode ──────────────────────────────────────────────────

async function loadGuidedQuestions() {
  guidedLoading.value = true
  guidedError.value = null
  try {
    const result = await generateCardPrompt()
    guidedQuestions.value = result.questions
    guidedAnswers.value = new Array(result.questions.length).fill('')
    currentQuestionIndex.value = 0
  } catch (err) {
    guidedError.value = formatApiError(err, '加载引导问题失败')
    // Fallback questions
    guidedQuestions.value = [
      '今天让你印象最深的一件事是什么？',
      '这件事给你带来了什么感受？',
      '如果可以重来，你会怎么做？',
    ]
    guidedAnswers.value = new Array(3).fill('')
  } finally {
    guidedLoading.value = false
  }
}

function nextQuestion() {
  if (isLastQuestion.value) {
    saveGuidedCard()
    return
  }
  currentQuestionIndex.value++
}

function prevQuestion() {
  if (currentQuestionIndex.value > 0) {
    currentQuestionIndex.value--
  }
}

async function saveGuidedCard() {
  const allAnswers = guidedAnswers.value.filter(a => a.trim()).join('\n')
  selectedEmotion.value = '记录'
  eventSummary.value = allAnswers || '今天的记忆卡片'
  saving.value = true
  saveError.value = null

  try {
    const payload: CardCreatePayload = {
      emotion: '记录',
      event_summary: allAnswers || '今天的记忆卡片',
      mood_score: 0.6,
      tags: selectedTags.value,
      importance: 0.7,
      card_type: 'guided',
    }
    const card = await createCard(payload)
    savedCardId.value = card.card_id
    emit('saved', { ...payload, card_id: card.card_id })
    if (props.autoClose) {
      setTimeout(() => emit('close'), 800)
    }
  } catch (err) {
    saveError.value = formatApiError(err, copy.saveError)
  } finally {
    saving.value = false
  }
}

// ── Lifecycle ────────────────────────────────────────────────────

onMounted(() => {
  if (isGuidedMode.value) {
    loadGuidedQuestions()
  }
})

defineExpose({ reset, saveCard })
</script>

<template>
  <div class="mcard-root">
    <!-- ── Emotion selector ─────────────────────────────────────── -->
    <div class="mcard-section">
      <p class="mcard-label">{{ copy.emotionLabel }}</p>

      <div class="mcard-emotions">
        <button
          v-for="emotion in PRESET_EMOTIONS"
          :key="emotion.key"
          class="mcard-emotion-chip"
          :class="{
            'mcard-emotion-chip--selected': selectedEmotion === emotion.key && !showCustomInput,
            'mcard-emotion-chip--high': emotion.moodScore >= 0.7,
            'mcard-emotion-chip--mid': emotion.moodScore >= 0.4 && emotion.moodScore < 0.7,
            'mcard-emotion-chip--low': emotion.moodScore < 0.4,
          }"
          :aria-label="emotion.key"
          @click="selectEmotion(emotion.key)"
        >
          <span class="mcard-emotion-icon">{{ emotion.key.slice(0, 1) }}</span>
          <span class="mcard-emotion-label">{{ emotion.key }}</span>
        </button>

        <button
          v-if="!showCustomInput"
          class="mcard-emotion-chip mcard-emotion-chip--custom"
          @click="startCustomEmotion"
        >
          <PhPlus :size="14" weight="bold" />
          <span class="mcard-emotion-label">{{ copy.tagsPlaceholder.slice(0, 4) }}</span>
        </button>
      </div>

      <!-- Custom emotion input -->
      <div v-if="showCustomInput" class="mcard-custom-row">
        <input
          v-model="customEmotion"
          class="mcard-custom-input"
          :placeholder="copy.emotionPlaceholder"
          maxlength="32"
          @keydown.enter="confirmCustomEmotion"
        />
        <button class="mcard-custom-btn mcard-custom-btn--ok" @click="confirmCustomEmotion">
          <PhCheck :size="14" weight="bold" />
        </button>
        <button class="mcard-custom-btn mcard-custom-btn--cancel" @click="cancelCustomEmotion">
          <PhX :size="14" />
        </button>
      </div>
    </div>

    <!-- ── Event summary (standard mode) ────────────────────────── -->
    <div v-if="mode === 'standard'" class="mcard-section">
      <p class="mcard-label">{{ copy.eventLabel }}</p>
      <textarea
        v-model="eventSummary"
        class="mcard-textarea"
        :placeholder="copy.eventPlaceholder"
        rows="2"
        maxlength="280"
      />
      <p class="mcard-hint">{{ eventSummary.length }}/280</p>
    </div>

    <!-- ── Tags (standard mode) ─────────────────────────────────── -->
    <div v-if="mode === 'standard'" class="mcard-section">
      <p class="mcard-label">{{ copy.tagsLabel }}</p>
      <div class="mcard-tags">
        <button
          v-for="tag in QUICK_TAGS"
          :key="tag.key"
          class="mcard-tag-chip"
          :class="{ 'mcard-tag-chip--selected': selectedTags.includes(tag.key) }"
          @click="toggleTag(tag.key)"
        >
          {{ tag.key }}
        </button>
      </div>
    </div>

    <!-- ── Guided mode ───────────────────────────────────────────── -->
    <div v-if="mode === 'guided'" class="mcard-section mcard-guided">
      <!-- Loading -->
      <div v-if="guidedLoading" class="mcard-guided-loading">
        <PhSpinner :size="18" weight="bold" />
        <span>正在生成个性化问题……</span>
      </div>

      <!-- Error -->
      <div v-else-if="guidedError" class="mcard-guided-error">{{ guidedError }}</div>

      <!-- Questions -->
      <template v-else-if="hasMoreQuestions">
        <div class="mcard-guided-progress">
          问题 {{ currentQuestionIndex + 1 }} / {{ guidedQuestions.length }}
        </div>
        <p class="mcard-guided-text">{{ currentQuestion }}</p>
        <textarea
          v-model="guidedAnswers[currentQuestionIndex]"
          class="mcard-guided-answer"
          :placeholder="'写下你的回答……'"
          rows="3"
        />
        <div class="mcard-guided-nav">
          <button
            v-if="currentQuestionIndex > 0"
            class="mcard-guided-nav-btn"
            @click="prevQuestion"
          >
            <PhArrowLeft :size="14" />
            上一题
          </button>
          <div v-else />
          <button
            class="mcard-guided-nav-btn mcard-guided-nav-btn--next"
            @click="nextQuestion"
          >
            {{ isLastQuestion ? '完成' : '下一题' }}
            <PhArrowRight :size="14" />
          </button>
        </div>
      </template>
    </div>

    <!-- ── Save action ──────────────────────────────────────────── -->
    <div class="mcard-actions">
      <div v-if="saveError" class="mcard-error">{{ saveError }}</div>
      <div v-else-if="savedCardId" class="mcard-success">
        {{ copy.cardSaved }}
      </div>

      <GameButton
        v-if="mode !== 'quick'"
        variant="primary"
        :disabled="!canSave || saving"
        @click="saveCard"
      >
        <template v-if="saving">
          <PhSpinner :size="14" weight="bold" />
        </template>
        <template v-else>
          <PhFloppyDisk :size="14" />
        </template>
        {{ saving ? '保存中\u2026' : copy.saveCard }}
      </GameButton>
    </div>
  </div>
</template>

<style scoped>
/* ── Root ──────────────────────────────────────────────── */
.mcard-root {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

/* ── Section ───────────────────────────────────────────── */
.mcard-section { }

.mcard-label {
  font-family: var(--font-ui);
  font-size: 0.8125rem;
  font-weight: 700;
  color: var(--color-accent);
  margin-bottom: 0.625rem;
}

/* ── Emotions ──────────────────────────────────────────── */
.mcard-emotions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.mcard-emotion-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.4375rem 0.75rem;
  border-radius: var(--radius-button, 0.75rem);
  border: 1px solid var(--color-border);
  background: var(--color-bg-elevated);
  cursor: pointer;
  transition: all var(--motion-duration, 220ms) var(--motion-ease, ease);
  font-family: var(--font-ui);
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
}

.mcard-emotion-chip:hover {
  border-color: var(--color-accent);
  color: var(--color-accent);
}

.mcard-emotion-chip--selected {
  border-color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 12%, transparent);
  color: var(--color-accent);
  font-weight: 600;
}

.mcard-emotion-chip--high.mcard-emotion-chip--selected {
  background: color-mix(in srgb, var(--color-success) 12%, transparent);
  border-color: var(--color-success);
  color: var(--color-success);
}

.mcard-emotion-chip--low.mcard-emotion-chip--selected {
  background: color-mix(in srgb, var(--color-warning) 12%, transparent);
  border-color: var(--color-warning);
  color: var(--color-warning);
}

.mcard-emotion-chip--custom {
  border-style: dashed;
}

.mcard-emotion-icon {
  font-size: 0.9375rem;
  line-height: 1;
}

.mcard-emotion-label {
  white-space: nowrap;
}

/* ── Custom emotion ──────────────────────────────────────── */
.mcard-custom-row {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  margin-top: 0.5rem;
}

.mcard-custom-input {
  flex: 1;
  padding: 0.5rem 0.75rem;
  border-radius: var(--radius-button, 0.75rem);
  border: 1px solid var(--color-accent);
  background: var(--color-bg);
  color: var(--color-text-primary);
  font-family: var(--font-ui);
  font-size: 0.875rem;
  outline: none;
}

.mcard-custom-input::placeholder {
  color: var(--color-text-secondary);
  opacity: 0.6;
}

.mcard-custom-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.875rem;
  height: 1.875rem;
  border-radius: 50%;
  border: 1px solid var(--color-border);
  cursor: pointer;
  transition: all var(--motion-duration, 220ms) var(--motion-ease, ease);
}

.mcard-custom-btn--ok {
  background: var(--color-accent);
  border-color: var(--color-accent);
  color: #fff;
}

.mcard-custom-btn--cancel {
  background: transparent;
  color: var(--color-text-secondary);
}

/* ── Textarea ───────────────────────────────────────────── */
.mcard-textarea {
  width: 100%;
  padding: 0.625rem 0.75rem;
  border-radius: var(--radius-button, 0.75rem);
  border: 1px solid var(--color-border);
  background: var(--color-bg);
  color: var(--color-text-primary);
  font-family: var(--font-diary);
  font-size: 0.9375rem;
  line-height: 1.6;
  resize: none;
  outline: none;
  transition: border-color var(--motion-duration, 220ms) var(--motion-ease, ease);
}

.mcard-textarea:focus {
  border-color: var(--color-accent);
}

.mcard-textarea::placeholder {
  color: var(--color-text-secondary);
  opacity: 0.5;
  font-family: var(--font-diary);
}

.mcard-hint {
  font-family: var(--font-ui);
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
  text-align: right;
  margin-top: 0.25rem;
}

/* ── Tags ───────────────────────────────────────────────── */
.mcard-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4375rem;
}

.mcard-tag-chip {
  display: inline-flex;
  align-items: center;
  padding: 0.3125rem 0.75rem;
  border-radius: 1rem;
  border: 1px solid var(--color-border);
  background: var(--color-bg-elevated);
  cursor: pointer;
  font-family: var(--font-ui);
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  transition: all var(--motion-duration, 220ms) var(--motion-ease, ease);
}

.mcard-tag-chip:hover {
  border-color: var(--color-accent-muted);
  color: var(--color-accent);
}

.mcard-tag-chip--selected {
  border-color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 15%, transparent);
  color: var(--color-accent);
  font-weight: 600;
}

/* ── Guided ──────────────────────────────────────────────── */
.mcard-guided {
  padding: 1rem;
  border-radius: var(--radius-button, 0.75rem);
  background: var(--color-bg-elevated-2);
}

.mcard-guided-loading {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-family: var(--font-ui);
  font-size: 0.875rem;
  color: var(--color-text-secondary);
  padding: 0.5rem 0;
}

.mcard-guided-error {
  font-family: var(--font-ui);
  font-size: 0.8125rem;
  color: var(--color-danger);
}

.mcard-guided-progress {
  font-family: var(--font-ui);
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
  margin-bottom: 0.5rem;
}

.mcard-guided-text {
  font-family: var(--font-diary);
  font-size: 0.9375rem;
  color: var(--color-text-primary);
  line-height: 1.7;
  margin-bottom: 0.75rem;
}

.mcard-guided-answer {
  width: 100%;
  padding: 0.625rem 0.75rem;
  border-radius: var(--radius-button, 0.75rem);
  border: 1px solid var(--color-border);
  background: var(--color-bg);
  color: var(--color-text-primary);
  font-family: var(--font-diary);
  font-size: 0.9375rem;
  line-height: 1.6;
  resize: none;
  outline: none;
  transition: border-color var(--motion-duration, 220ms);
}

.mcard-guided-answer:focus {
  border-color: var(--color-accent);
}

.mcard-guided-answer::placeholder {
  color: var(--color-text-secondary);
  opacity: 0.5;
}

.mcard-guided-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 0.75rem;
}

.mcard-guided-nav-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.4375rem 0.875rem;
  border-radius: var(--radius-button, 0.75rem);
  border: 1px solid var(--color-border);
  background: var(--color-bg);
  color: var(--color-text-secondary);
  cursor: pointer;
  font-family: var(--font-ui);
  font-size: 0.8125rem;
  transition: all var(--motion-duration, 220ms);
}

.mcard-guided-nav-btn:hover {
  border-color: var(--color-accent);
  color: var(--color-accent);
}

.mcard-guided-nav-btn--next {
  border-color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 12%, transparent);
  color: var(--color-accent);
  font-weight: 600;
}

/* ── Actions ─────────────────────────────────────────────── */
.mcard-actions {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 0.75rem;
  padding-top: 0.375rem;
}

.mcard-error {
  font-family: var(--font-ui);
  font-size: 0.75rem;
  color: var(--color-danger);
  flex: 1;
}

.mcard-success {
  font-family: var(--font-ui);
  font-size: 0.75rem;
  color: var(--color-success);
  flex: 1;
  font-weight: 600;
}
</style>
