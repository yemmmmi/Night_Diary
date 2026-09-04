<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { chatCopy } from '@/shared/copy/chat'

defineProps<{
  disabled?: boolean
}>()

const emit = defineEmits<{
  send: [text: string]
}>()

const text = ref('')
const fieldEl = ref<HTMLTextAreaElement | null>(null)

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

/* 供空态 skill 起手卡调用：填入引导句并聚焦到行尾 */
function prefill(value: string) {
  text.value = value
  nextTick(() => {
    const el = fieldEl.value
    if (!el) return
    el.focus()
    el.setSelectionRange(el.value.length, el.value.length)
  })
}

defineExpose({ prefill })
</script>

<template>
  <div class="letter-composer">
    <div class="letter-composer__box" data-testid="letter-input">
      <textarea
        ref="fieldEl"
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
/* 圆棱方框回信输入：纸上的一只浅盒，落笔时描边点亮 */
.letter-composer {
  display: flex;
  align-items: flex-end;
  gap: 0.75rem;
}

.letter-composer__box {
  flex: 1;
  min-width: 0;
  padding: 0.5rem 0.875rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-inner);
  background: var(--color-bg-elevated);
  transition: border-color var(--motion-duration) var(--motion-ease),
    box-shadow var(--motion-duration) var(--motion-ease);
}

.letter-composer__box:focus-within {
  border-color: color-mix(in srgb, var(--color-accent) 55%, var(--color-border));
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--color-accent) 15%, transparent);
}

.letter-composer__field {
  display: block;
  width: 100%;
  border: none;
  background: transparent;
  padding: 0;
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
  border: 1px solid var(--color-border);
  background: var(--color-bg-elevated);
  padding: 0.4375rem 0.875rem;
  border-radius: var(--radius-button);
  flex-shrink: 0;
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition:
    border-color var(--motion-duration) var(--motion-ease),
    color var(--motion-duration) var(--motion-ease),
    background var(--motion-duration) var(--motion-ease);
}

.letter-composer__send:hover:not(:disabled) {
  border-color: color-mix(in srgb, var(--color-accent) 45%, var(--color-border));
  color: var(--color-text-primary);
}

.letter-composer__send:disabled {
  opacity: 0.35;
  cursor: default;
}
</style>
