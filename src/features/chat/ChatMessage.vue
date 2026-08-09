<script setup lang="ts">
import { computed } from 'vue'

import type { ChatMessage } from '@/shared/api/conversation'
import { chatCopy } from '@/shared/copy/chat'
import type { RenderSegment } from '@/shared/composables/useStreamingReply'
import PlanProposalCard from './PlanProposalCard.vue'
import ClarificationCard from './ClarificationCard.vue'

const props = defineProps<{
  message: ChatMessage
  diaryLabels?: Record<number, string>
  /** 流式协议块段：仅对正在/刚结束的 assistant 流式消息传入。
   *  历史消息（从 DB 加载）不传，仍走纯文本渲染。 */
  segments?: RenderSegment[]
  conversationId?: string
}>()

const referenceLabels = computed(() => {
  const ids = props.message.retrieved_diary_ids ?? []
  if (ids.length === 0) return []
  return ids.map((id) => props.diaryLabels?.[id] ?? `#${id}`)
})

const hasSegments = computed(
  () => Array.isArray(props.segments) && props.segments.length > 0,
)
</script>

<template>
  <div class="chat-msg" :class="`chat-msg--${message.role}`">
    <!-- 有协议块段时按段渲染（流式消息）；否则纯文本（历史消息） -->
    <template v-if="hasSegments">
      <template v-for="(seg, i) in segments" :key="i">
        <p v-if="seg.kind === 'text'" class="chat-msg__content">{{ seg.content }}</p>
        <PlanProposalCard
          v-else-if="seg.kind === 'protocol_block' && seg.blockType === 'plan_proposal'"
          :proposal="seg.data as any"
          :conversation-id="conversationId"
        />
        <ClarificationCard
          v-else-if="
            seg.kind === 'protocol_block' && seg.blockType === 'clarification_request'
          "
          :clarification="seg.data as any"
        />
      </template>
    </template>
    <p v-else class="chat-msg__content">{{ message.content }}</p>

    <p
      v-if="message.role === 'assistant' && referenceLabels.length > 0"
      class="chat-msg__refs"
    >
      {{ chatCopy.messageReferences }}：{{ referenceLabels.join('、') }}
    </p>
  </div>
</template>

<style scoped>
.chat-msg {
  max-width: 85%;
  padding: 0.625rem 0.875rem;
  border-radius: 0.75rem;
  font-size: 0.875rem;
  line-height: 1.6;
}

.chat-msg--user {
  align-self: flex-end;
  background: color-mix(in srgb, var(--color-accent) 12%, var(--color-bg-elevated));
  border: 1px solid color-mix(in srgb, var(--color-accent) 25%, var(--color-border));
  color: var(--color-text-primary);
}

.chat-msg--assistant {
  align-self: flex-start;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  font-family: var(--font-diary);
  color: var(--color-text-primary);
}

.chat-msg__content {
  white-space: pre-wrap;
}

.chat-msg__refs {
  margin-top: 0.5rem;
  padding-top: 0.375rem;
  border-top: 1px solid var(--color-border);
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
}
</style>
