<script setup lang="ts">
import { computed, ref } from 'vue'

import type { ChatMessage } from '@/shared/api/conversation'
import { chatCopy } from '@/shared/copy/chat'
import { parseServerTime } from '@/shared/utils/timeFormat'

const props = defineProps<{
  message: ChatMessage
  diaryLabels?: Record<number, string>
  cardLabels?: Record<string, string>
  planLabels?: Record<string, string>
  /** 信末操作行只渲染在最新一封夜记来信上（安静原则：不逐信挂链）。 */
  showActions?: boolean
  generating?: boolean
  generated?: boolean
}>()

const emit = defineEmits<{
  generateCard: []
}>()

const isNight = computed(() => props.message.role === 'assistant')

const signature = computed(() =>
  props.message.role === 'user' ? chatCopy.signatureUser : chatCopy.signatureNight,
)

const timeLabel = computed(() => {
  const date = parseServerTime(props.message.created_at)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
})

const noteItems = computed(() => {
  if (props.message.role !== 'assistant') return []
  const ids = props.message.retrieved_diary_ids ?? []
  return ids.map((id) => props.diaryLabels?.[id] ?? `日记 #${id}`)
})

/* 我的信的附物注脚：附上的卡片与计划（日记钉在回信侧以 retrieved 呈现） */
const attachNoteItems = computed(() => {
  if (props.message.role !== 'user') return []
  const items: string[] = []
  for (const cardId of props.message.attached_card_ids ?? []) {
    items.push(props.cardLabels?.[cardId] ?? `卡片 #${cardId.slice(0, 6)}`)
  }
  for (const planId of props.message.attached_plan_ids ?? []) {
    items.push(props.planLabels?.[planId] ?? `计划 #${planId.slice(0, 6)}`)
  }
  return items
})

const attachNoteLabel = computed(() =>
  chatCopy.letterAttachNote(
    (props.message.attached_card_ids ?? []).length,
    (props.message.attached_plan_ids ?? []).length,
  ),
)

const noteOpen = ref(false)
const attachNoteOpen = ref(false)

function toggleNote() {
  noteOpen.value = !noteOpen.value
}

function toggleAttachNote() {
  attachNoteOpen.value = !attachNoteOpen.value
}

function onGenerateCard() {
  if (props.generating) return
  emit('generateCard')
}
</script>

<template>
  <article
    class="letter"
    :class="`letter--${message.role}`"
    data-testid="letter"
  >
    <header class="letter__head">
      <span class="letter__signature">{{ signature }}</span>
      <time class="letter__time">{{ timeLabel }}</time>
    </header>

    <p class="letter__body">{{ message.content }}</p>

    <div v-if="noteItems.length > 0" class="letter-note" data-testid="letter-note">
      <button
        type="button"
        class="letter-note__toggle"
        :aria-expanded="noteOpen"
        @click="toggleNote"
      >
        {{ chatCopy.letterNoteCount(noteItems.length) }}
      </button>
      <ul v-if="noteOpen" class="letter-note__list">
        <li
          v-for="(item, index) in noteItems"
          :key="index"
          class="letter-note__item"
          data-testid="letter-note-item"
        >
          {{ item }}
        </li>
      </ul>
    </div>

    <div
      v-else-if="attachNoteItems.length > 0"
      class="letter-note letter-note--attach"
      data-testid="letter-attach-note"
    >
      <button
        type="button"
        class="letter-note__toggle"
        :aria-expanded="attachNoteOpen"
        @click="toggleAttachNote"
      >
        {{ attachNoteLabel }}
      </button>
      <ul v-if="attachNoteOpen" class="letter-note__list">
        <li
          v-for="(item, index) in attachNoteItems"
          :key="index"
          class="letter-note__item"
          data-testid="letter-attach-note-item"
        >
          {{ item }}
        </li>
      </ul>
    </div>

    <footer v-if="isNight && showActions" class="letter__foot">
      <span v-if="generated" class="letter__saved">{{ chatCopy.cardSavedInline }}</span>
      <button
        v-else
        type="button"
        class="letter__link"
        data-testid="letter-card-link"
        :disabled="generating"
        @click="onGenerateCard"
      >
        {{ generating ? chatCopy.cardGenerating : chatCopy.generateCard }}
      </button>
    </footer>
  </article>
</template>

<style scoped>
/* 往复书信：无气泡，信与信之间以细线相隔，正文文楷直排纵深感靠留白 */
.letter {
  padding: 0.875rem 0 0.75rem;
  border-top: 1px solid var(--color-line);
}

.letter__head {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  font-size: 0.6875rem;
}

/* 落款区分：我的信落款靠右，夜记的信落款靠左 */
.letter--user .letter__head {
  justify-content: flex-end;
}

.letter--assistant .letter__head {
  justify-content: flex-start;
}

.letter__signature {
  font-size: 0.8125rem;
  color: var(--color-text-primary);
}

.letter--assistant .letter__signature {
  font-family: var(--font-diary);
}

.letter__time {
  color: var(--color-text-faint);
}

.letter__body {
  margin: 0.375rem 0 0;
  font-family: var(--font-diary);
  font-size: 0.9375rem;
  line-height: 1.95;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--color-text-primary);
}

/* 页边注：左侧 accent 竖线 + 小字，默认收起 */
.letter-note {
  margin-top: 0.625rem;
  padding-left: 0.625rem;
  border-left: 2px solid var(--color-accent-muted);
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
}

/* 我的信的附物注脚：虚线竖线，与回信侧参考注脚区分 */
.letter-note--attach {
  border-left-style: dashed;
}

.letter-note__toggle {
  border: none;
  background: none;
  padding: 0;
  font-size: inherit;
  color: inherit;
  text-decoration: underline dotted;
  text-underline-offset: 3px;
  cursor: pointer;
}

.letter-note__toggle:hover {
  color: var(--color-text-primary);
}

.letter-note__list {
  margin: 0.375rem 0 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.letter-note__item {
  line-height: 1.5;
}

.letter__foot {
  margin-top: 0.5rem;
}

.letter__link {
  border: none;
  background: none;
  padding: 0;
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
  text-decoration: underline;
  text-underline-offset: 3px;
  cursor: pointer;
}

.letter__link:hover:not(:disabled) {
  color: var(--color-text-primary);
}

.letter__link:disabled {
  opacity: 0.5;
  cursor: default;
}

/* 生成成功后的行内淡墨提示：不弹窗、不喧哗 */
.letter__saved {
  font-size: 0.6875rem;
  color: var(--color-text-faint);
}
</style>
