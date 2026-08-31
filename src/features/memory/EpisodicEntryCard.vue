<script setup lang="ts">
import { ref, watch } from 'vue'
import { PhPencilSimple, PhTrash, PhCheck, PhX, PhArrowRight } from '@phosphor-icons/vue'

import EmotionChips from '@/features/card/EmotionChips.vue'
import { memoryCopy as copy } from '@/shared/copy/memory'
import type { EpisodicEntry, EpisodicEntryUpdate } from '@/shared/api/memory'

const props = defineProps<{
  entry: EpisodicEntry
  sourceLabel: string
  formattedTime: string
  saving?: boolean
}>()

const emit = defineEmits<{
  save: [entryId: string, patch: EpisodicEntryUpdate]
  delete: [entryId: string]
  viewDiary: [diaryId: string]
}>()

const editing = ref(false)
const draftEvent = ref('')
const draftEmotion = ref('')
const draftSuggestion = ref('')
const draftImportance = ref(50)

function startEdit() {
  draftEvent.value = props.entry.event_summary
  draftEmotion.value = props.entry.emotion
  draftSuggestion.value = props.entry.reply_insight
  draftImportance.value = Math.round(props.entry.importance * 100)
  editing.value = true
}

function cancelEdit() {
  editing.value = false
}

function onSave() {
  const event = draftEvent.value.trim()
  const emotion = draftEmotion.value.trim()
  if (!event || !emotion) return
  emit('save', props.entry.entry_id, {
    event_summary: event,
    emotion,
    reply_insight: draftSuggestion.value.trim(),
    importance: draftImportance.value / 100,
  })
}

watch(
  () => props.entry.entry_id,
  () => {
    editing.value = false
  },
)

watch(
  () => [props.entry.event_summary, props.entry.emotion, props.entry.reply_insight, props.entry.importance],
  () => {
    if (editing.value) editing.value = false
  },
)

defineExpose({ cancelEdit })
</script>

<template>
  <article class="episodic-row" data-testid="episodic-row">
    <div class="episodic-row__head">
      <EmotionChips v-if="!editing" :emotion="entry.emotion" :size="13" />
      <div v-if="!editing" class="episodic-row__actions">
        <button
          type="button"
          class="episodic-row__icon-btn"
          :aria-label="copy.editEntry"
          @click="startEdit"
        >
          <PhPencilSimple :size="15" />
        </button>
        <button
          type="button"
          class="episodic-row__icon-btn episodic-row__icon-btn--danger"
          :aria-label="copy.deleteEntry"
          @click="emit('delete', entry.entry_id)"
        >
          <PhTrash :size="15" />
        </button>
      </div>
    </div>

    <template v-if="editing">
      <label class="episodic-row__field">
        <span>{{ copy.editEvent }}</span>
        <textarea v-model="draftEvent" rows="3" class="episodic-row__textarea" />
      </label>
      <label class="episodic-row__field">
        <span>{{ copy.editEmotion }}</span>
        <input v-model="draftEmotion" type="text" maxlength="32" class="episodic-row__input" />
      </label>
      <label v-if="entry.source === 'diary'" class="episodic-row__field">
        <span>{{ copy.editSuggestion }}</span>
        <textarea v-model="draftSuggestion" rows="2" class="episodic-row__textarea" />
      </label>
      <label class="episodic-row__field">
        <span>{{ copy.importance }} {{ draftImportance }}%</span>
        <input v-model.number="draftImportance" type="range" min="0" max="100" step="5" />
      </label>
      <div class="episodic-row__edit-actions">
        <button
          type="button"
          class="episodic-row__edit-btn episodic-row__edit-btn--primary"
          :disabled="saving || !draftEvent.trim() || !draftEmotion.trim()"
          @click="onSave"
        >
          <PhCheck :size="14" />
          {{ copy.saveEntry }}
        </button>
        <button
          type="button"
          class="episodic-row__edit-btn"
          :disabled="saving"
          @click="cancelEdit"
        >
          <PhX :size="14" />
          {{ copy.cancelEdit }}
        </button>
      </div>
    </template>

    <template v-else>
      <p class="episodic-row__event font-diary">{{ entry.event_summary }}</p>
      <!-- AI 建议改页边注：左侧 accent 竖线 + 小字，只陈述不评判 -->
      <p v-if="entry.reply_insight" class="episodic-row__note">{{ entry.reply_insight }}</p>
      <div class="episodic-row__footer">
        <span class="episodic-row__time">{{ formattedTime }}</span>
        <span class="episodic-row__meta">
          {{ sourceLabel }} · {{ copy.importance }} {{ (entry.importance * 100).toFixed(0) }}%
        </span>
        <button
          v-if="entry.diary_ids.length"
          type="button"
          class="episodic-row__link"
          @click="emit('viewDiary', entry.diary_ids[0])"
        >
          {{ copy.viewDiary }}
          <PhArrowRight :size="12" weight="bold" />
        </button>
      </div>
    </template>
  </article>
</template>

<style scoped>
/* 情节记忆细线行：无卡片底，只以底线分隔 */
.episodic-row {
  padding: 0.875rem 0;
  border-bottom: 1px solid var(--color-line);
}

.episodic-row:last-child {
  border-bottom: none;
}

.episodic-row__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.375rem;
}

.episodic-row__actions {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  margin-left: auto;
}

.episodic-row__icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.75rem;
  height: 1.75rem;
  border: none;
  border-radius: var(--radius-seal);
  background: transparent;
  color: var(--color-text-faint);
  cursor: pointer;
  transition: color var(--dur-fast) var(--ease-out-quart);
}

.episodic-row__icon-btn:hover {
  color: var(--color-text-primary);
}

.episodic-row__icon-btn--danger:hover {
  color: var(--color-danger);
}

.episodic-row__event {
  margin: 0;
  font-size: 0.9375rem;
  line-height: 1.9;
  color: var(--color-text-primary);
}

/* 页边注：左侧 2px 竖线 + 小字 */
.episodic-row__note {
  margin: 0.5rem 0 0;
  padding-left: 0.625rem;
  border-left: 2px solid var(--color-accent);
  font-size: 0.75rem;
  line-height: 1.7;
  color: var(--color-text-secondary);
}

.episodic-row__footer {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-top: 0.5rem;
  font-size: 0.6875rem;
  color: var(--color-text-faint);
}

.episodic-row__meta {
  font-variant-numeric: tabular-nums;
}

.episodic-row__time {
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.02em;
}

/* 查看原文：淡墨下划线文字链 */
.episodic-row__link {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0;
  border: none;
  background: transparent;
  font-size: 0.6875rem;
  color: var(--color-text-faint);
  text-decoration: underline;
  text-underline-offset: 0.1875rem;
  cursor: pointer;
  transition: color var(--dur-fast) var(--ease-out-quart);
}

.episodic-row__link:hover {
  color: var(--color-text-secondary);
}

/* ── 行内编辑 ─────────────────────────────────────────────────── */
.episodic-row__field {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  margin-bottom: 0.75rem;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

.episodic-row__textarea,
.episodic-row__input {
  padding: 0.5rem 0.625rem;
  border: 1px solid var(--color-line);
  border-radius: var(--radius-seal);
  background: var(--color-diary-surface);
  color: var(--color-text-primary);
  font-family: var(--font-ui);
  font-size: 0.8125rem;
  resize: vertical;
}

.episodic-row__textarea:focus,
.episodic-row__input:focus {
  outline: none;
  border-color: var(--color-accent);
}

.episodic-row__edit-actions {
  display: flex;
  gap: 0.75rem;
}

.episodic-row__edit-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 0.75rem;
  cursor: pointer;
  transition: color var(--dur-fast) var(--ease-out-quart);
}

.episodic-row__edit-btn--primary {
  color: var(--color-accent);
  font-weight: 600;
}

.episodic-row__edit-btn:hover:not(:disabled) {
  color: var(--color-text-primary);
}

.episodic-row__edit-btn--primary:hover:not(:disabled) {
  color: var(--color-accent-muted);
}

.episodic-row__edit-btn:disabled {
  opacity: 0.5;
  cursor: default;
}
</style>
