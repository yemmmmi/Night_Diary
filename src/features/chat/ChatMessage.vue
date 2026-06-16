<script setup lang="ts">
import type { ChatMessage } from '@/shared/api/conversation'

defineProps<{
  message: ChatMessage
}>()
</script>

<template>
  <div class="chat-msg" :class="`chat-msg--${message.role}`">
    <p class="chat-msg__content">{{ message.content }}</p>
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
</style>
