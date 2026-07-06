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
  <article class="memory-entry glass-panel">
    <div class="memory-entry__head">
      <EmotionChips v-if="!editing" :emotion="entry.emotion" :size="13" />
      <span
        v-if="!editing"
        class="memory-entry__source"
        :class="`memory-entry__source--${entry.source}`"
      >
        {{ sourceLabel }}
      </span>
      <div v-if="!editing" class="memory-entry__actions">
        <button
          type="button"
          class="memory-entry__icon-btn"
          :aria-label="copy.editEntry"
          @click="startEdit"
        >
          <PhPencilSimple :size="15" />
        </button>
        <button
          type="button"
          class="memory-entry__icon-btn memory-entry__icon-btn--danger"
          :aria-label="copy.deleteEntry"
          @click="emit('delete', entry.entry_id)"
        >
          <PhTrash :size="15" />
        </button>
      </div>
    </div>

    <template v-if="editing">
      <label class="memory-entry__field">
        <span>{{ copy.editEvent }}</span>
        <textarea v-model="draftEvent" rows="3" class="memory-entry__textarea" />
      </label>
      <label class="memory-entry__field">
        <span>{{ copy.editEmotion }}</span>
        <input v-model="draftEmotion" type="text" maxlength="32" class="memory-entry__input" />
      </label>
      <label v-if="entry.source === 'diary'" class="memory-entry__field">
        <span>{{ copy.editSuggestion }}</span>
        <textarea v-model="draftSuggestion" rows="2" class="memory-entry__textarea" />
      </label>
      <label class="memory-entry__field">
        <span>{{ copy.importance }} {{ draftImportance }}%</span>
        <input v-model.number="draftImportance" type="range" min="0" max="100" step="5" />
      </label>
      <div class="memory-entry__edit-actions">
        <button
          type="button"
          class="memory-entry__edit-btn memory-entry__edit-btn--primary"
          :disabled="saving || !draftEvent.trim() || !draftEmotion.trim()"
          @click="onSave"
        >
          <PhCheck :size="14" />
          {{ copy.saveEntry }}
        </button>
        <button
          type="button"
          class="memory-entry__edit-btn"
          :disabled="saving"
          @click="cancelEdit"
        >
          <PhX :size="14" />
          {{ copy.cancelEdit }}
        </button>
      </div>
    </template>

    <template v-else>
      <p class="memory-entry__event font-diary">{{ entry.event_summary }}</p>
      <p v-if="entry.reply_insight" class="memory-entry__suggestion">
        {{ entry.reply_insight }}
      </p>
      <div class="memory-entry__footer">
        <span class="memory-entry__time">{{ formattedTime }}</span>
        <div class="memory-entry__footer-right">
          <span class="memory-entry__importance">
            {{ copy.importance }} {{ (entry.importance * 100).toFixed(0) }}%
          </span>
          <button
            v-if="entry.diary_ids.length"
            type="button"
            class="memory-entry__link"
            @click="emit('viewDiary', entry.diary_ids[0])"
          >
            {{ copy.viewDiary }}
            <PhArrowRight :size="12" weight="bold" />
          </button>
        </div>
      </div>
    </template>
  </article>
</template>

<style scoped>
.memory-entry {
  padding: 0.875rem 1rem;
  border-radius: var(--radius-button, 0.75rem);
}

.memory-entry__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.memory-entry__actions {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  margin-left: auto;
}

.memory-entry__icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.75rem;
  height: 1.75rem;
  border: none;
  border-radius: 0.375rem;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: background var(--motion-duration, 220ms) var(--motion-ease, ease);
}

.memory-entry__icon-btn:hover {
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
}

.memory-entry__icon-btn--danger:hover {
  color: var(--color-danger);
}

.memory-entry__source {
  font-size: 0.6875rem;
  font-weight: 600;
  padding: 0.125rem 0.5rem;
  border-radius: 1rem;
}

.memory-entry__source--card {
  color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 12%, transparent);
}

.memory-entry__source--diary {
  color: var(--color-text-secondary);
  background: var(--color-bg-elevated);
}

.memory-entry__event {
  font-size: 0.9375rem;
  line-height: 1.7;
  color: var(--color-text-primary);
}

.memory-entry__suggestion {
  margin-top: 0.5rem;
  padding: 0.5rem 0.75rem;
  border-radius: 0.5rem;
  background: var(--color-bg-elevated);
  font-size: 0.8125rem;
  line-height: 1.6;
  color: var(--color-text-secondary);
}

.memory-entry__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 0.625rem;
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
}

.memory-entry__footer-right {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.memory-entry__link {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.125rem 0.5rem;
  border: none;
  border-radius: 1rem;
  background: transparent;
  font-size: 0.6875rem;
  font-weight: 600;
  color: var(--color-accent);
  cursor: pointer;
  transition: background var(--motion-duration, 220ms) var(--motion-ease, ease);
}

.memory-entry__link:hover {
  background: color-mix(in srgb, var(--color-accent) 12%, transparent);
}

.memory-entry__field {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  margin-bottom: 0.75rem;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

.memory-entry__textarea,
.memory-entry__input {
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: 0.5rem;
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
  font-family: var(--font-ui);
  font-size: 0.8125rem;
  resize: vertical;
}

.memory-entry__textarea:focus,
.memory-entry__input:focus {
  outline: none;
  border-color: var(--color-accent);
}

.memory-entry__edit-actions {
  display: flex;
  gap: 0.5rem;
}

.memory-entry__edit-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.4375rem 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: 0.5rem;
  background: var(--color-bg-elevated);
  color: var(--color-text-secondary);
  font-size: 0.75rem;
  cursor: pointer;
}

.memory-entry__edit-btn--primary {
  border-color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 12%, transparent);
  color: var(--color-accent);
  font-weight: 600;
}

.memory-entry__edit-btn:disabled {
  opacity: 0.5;
  cursor: default;
}
</style>
