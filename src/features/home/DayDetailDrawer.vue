<script setup lang="ts">
import type { DiaryEntry } from '@/shared/api/diary'
import type { MemoryCard } from '@/shared/api/card'
import EmotionChips from '@/features/card/EmotionChips.vue'
import { homeSceneCopy as copy } from '@/shared/copy/homeScene'
import { cardCopy } from '@/shared/copy/card'
import {
  diaryStatus,
  diaryStatusLabel,
  diarySummary,
} from '@/shared/utils/diaryFormat'
import type { KanbanItem } from '@/shared/utils/kanbanSort'

defineProps<{
  title: string
  items: KanbanItem[]
}>()

const emit = defineEmits<{
  close: []
  openDiary: [entry: DiaryEntry, scrollToReply?: boolean]
  openCard: [card: MemoryCard]
}>()

const EMOTION_COLORS: Record<string, string> = {
  开心: '#4CAF50',
  平静: '#607D8B',
  感激: '#D4A574',
  期待: '#26A69A',
  兴奋: '#FF9800',
  焦虑: '#7E57C2',
  疲惫: '#9E9E9E',
  悲伤: '#5C6BC0',
  迷茫: '#78909C',
  愤怒: '#EF5350',
}

function statusClass(status: ReturnType<typeof diaryStatus>) {
  return `day-drawer__chip--${status}`
}

function cardEmotionColor(card: MemoryCard): string {
  return EMOTION_COLORS[card.emotion] ?? 'var(--color-accent)'
}

function onDiaryClick(entry: DiaryEntry) {
  const scrollToReply = Boolean(entry.ai_ans?.trim())
  emit('openDiary', entry, scrollToReply)
}
</script>

<template>
  <div class="day-drawer-backdrop" @click.self="emit('close')">
    <aside class="day-drawer-panel" role="dialog" aria-modal="true">
      <header class="day-drawer__header">
        <h2 class="day-drawer__title">{{ title }}</h2>
        <button type="button" class="day-drawer__close" @click="emit('close')">&times;</button>
      </header>

      <div class="day-drawer__list">
        <button
          v-for="item in items"
          :key="item.kind === 'diary' ? `d-${item.entry.id}` : `c-${item.card.card_id}`"
          type="button"
          class="day-drawer__item"
          :class="{ 'day-drawer__item--card': item.kind === 'card' }"
          :style="item.kind === 'card' ? { borderLeftColor: cardEmotionColor(item.card) } : undefined"
          @click="item.kind === 'diary' ? onDiaryClick(item.entry) : emit('openCard', item.card)"
        >
          <template v-if="item.kind === 'diary'">
            <span class="day-drawer__summary">{{ diarySummary(item.entry.content, 48) }}</span>
            <div class="day-drawer__footer">
              <EmotionChips
                v-if="item.linkedCard"
                :emotions="item.linkedCard.emotions"
                :emotion="item.linkedCard.emotion"
                :size="12"
                compact
                :max-count="1"
              />
              <span class="day-drawer__chip" :class="statusClass(diaryStatus(item.entry))">
                {{ diaryStatusLabel(diaryStatus(item.entry)) }}
              </span>
            </div>
          </template>
          <template v-else>
            <span v-if="item.card.event_summary" class="day-drawer__summary">
              {{ diarySummary(item.card.event_summary, 48) }}
            </span>
            <span v-else class="day-drawer__summary day-drawer__summary--muted">
              {{ cardCopy.recordedMoodOnly }}
            </span>
            <div class="day-drawer__footer">
              <EmotionChips
                :emotions="item.card.emotions"
                :emotion="item.card.emotion"
                :size="12"
                compact
                :max-count="1"
              />
            </div>
          </template>
        </button>

        <p v-if="items.length === 0" class="day-drawer__empty">{{ copy.emptyDesc }}</p>
      </div>
    </aside>
  </div>
</template>

<style scoped>
.day-drawer-backdrop {
  position: fixed;
  inset: 0;
  z-index: 900;
  background: rgba(0, 0, 0, 0.3);
  display: flex;
  justify-content: flex-end;
}

.day-drawer-panel {
  width: min(22rem, 92vw);
  height: 100%;
  background: var(--color-bg-elevated);
  border-left: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  box-shadow: -8px 0 24px rgba(0, 0, 0, 0.08);
}

.day-drawer__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--color-border);
}

.day-drawer__title {
  font-size: 1rem;
  font-weight: 700;
  color: var(--color-text-primary);
}

.day-drawer__close {
  width: 1.75rem;
  height: 1.75rem;
  border: none;
  background: transparent;
  font-size: 1.25rem;
  color: var(--color-text-secondary);
  cursor: pointer;
  border-radius: 50%;
}

.day-drawer__close:hover {
  background: var(--color-bg-elevated-2);
}

.day-drawer__list {
  flex: 1;
  overflow-y: auto;
  padding: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.day-drawer__item {
  width: 100%;
  text-align: left;
  padding: 0.625rem 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: 0.625rem;
  background: var(--color-bg-elevated-2);
  cursor: pointer;
}

.day-drawer__item--card {
  border-left-width: 3px;
  border-left-style: solid;
}

.day-drawer__summary {
  display: block;
  font-size: 0.8125rem;
  line-height: 1.5;
  color: var(--color-text-primary);
}

.day-drawer__summary--muted {
  color: var(--color-text-secondary);
  font-style: italic;
}

.day-drawer__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 0.375rem;
}

.day-drawer__chip {
  margin-left: auto;
  border-radius: 999px;
  padding: 0.0625rem 0.375rem;
  font-size: 0.5625rem;
  font-weight: 600;
}

.day-drawer__chip--reply {
  background: color-mix(in srgb, var(--color-success) 18%, transparent);
  color: var(--color-success);
}

.day-drawer__chip--pending {
  background: color-mix(in srgb, var(--color-warning) 18%, transparent);
  color: var(--color-warning);
}

.day-drawer__chip--draft {
  background: color-mix(in srgb, var(--color-accent) 14%, transparent);
  color: var(--color-accent-muted);
}

.day-drawer__empty {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  text-align: center;
  padding: 2rem 1rem;
}
</style>
