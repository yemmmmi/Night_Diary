<script setup lang="ts">
import { ref } from 'vue'
import { chatCopy } from '@/shared/copy/chat'

defineProps<{
  disabled?: boolean
}>()

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
  <div class="letter-composer">
    <div class="letter-composer__line ink-underline" data-testid="letter-input">
      <textarea
        v-model="text"
        class="letter-composer__field"
        rows="1"
        :placeholder="chatCopy.inputPlaceholder"
        :disabled="disabled"
        @keydown="onKeydown"
      />
    </div>
    <button
      type="button"
      class="letter-composer__send"
      data-testid="letter-send"
      :disabled="!text.trim() || disabled"
      @click="onSend"
    >
      {{ chatCopy.sendLabel }}
    </button>
  </div>
</template>

<style scoped>
/* 底线式回信输入：正文落在纸上，只有一条会生长的底线 */
.letter-composer {
  display: flex;
  align-items: flex-end;
  gap: 0.75rem;
}

.letter-composer__line {
  flex: 1;
  min-width: 0;
}

/* ink-underline 的底线生长在包裹层上，用 focus-within 点亮 */
.letter-composer__line:focus-within::after {
  transform: scaleX(1);
}

.letter-composer__field {
  display: block;
  width: 100%;
  border: none;
  background: transparent;
  padding: 0.25rem 0;
  color: var(--color-text-primary);
  font-family: var(--font-diary);
  font-size: 0.9375rem;
  line-height: 1.8;
  resize: none;
  outline: none;
}

.letter-composer__field::placeholder {
  color: var(--color-text-faint);
}

.letter-composer__field:disabled {
  opacity: 0.6;
}

.letter-composer__send {
  border: none;
  background: none;
  padding: 0.25rem 0;
  flex-shrink: 0;
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  text-decoration: underline;
  text-underline-offset: 3px;
  cursor: pointer;
}

.letter-composer__send:hover:not(:disabled) {
  color: var(--color-text-primary);
}

.letter-composer__send:disabled {
  opacity: 0.35;
  cursor: default;
}
</style>
