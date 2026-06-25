<script setup lang="ts">
import { ref } from 'vue'
import { chatCopy } from '@/shared/copy/chat'

const emit = defineEmits<{
  send: [text: string]
}>()

const text = ref('')

function onSend() {
  const trimmed = text.value.trim()
  if (!trimmed) return
  emit('send', trimmed)
  text.value = ''
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    onSend()
  }
}
</script>

<template>
  <div class="chat-input">
    <textarea
      v-model="text"
      class="chat-input__field"
      rows="1"
      :placeholder="chatCopy.inputPlaceholder"
      @keydown="onKeydown"
    />
    <button
      type="button"
      class="chat-input__send"
      :disabled="!text.trim()"
      @click="onSend"
    >
      &#8617;
    </button>
  </div>
</template>

<style scoped>
.chat-input {
  display: flex;
  align-items: flex-end;
  gap: 0.5rem;
  flex-shrink: 0;
  padding: 0.625rem 0.75rem;
  border-top: 1px solid var(--color-border);
  background: var(--color-bg);
}

.chat-input__field {
  flex: 1;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: 0.75rem;
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
  font-family: var(--font-ui);
  font-size: 0.8125rem;
  resize: none;
  outline: none;
}

.chat-input__field:focus {
  border-color: var(--color-accent);
}

.chat-input__send {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  flex-shrink: 0;
  border: none;
  border-radius: 50%;
  background: var(--color-accent);
  color: #fff;
  font-size: 1rem;
  cursor: pointer;
  transition: opacity var(--motion-duration) var(--motion-ease);
}

.chat-input__send:disabled {
  opacity: 0.35;
  cursor: default;
}
</style>
