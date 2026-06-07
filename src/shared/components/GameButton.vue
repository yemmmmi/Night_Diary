<script setup lang="ts">
import { ref } from 'vue'

withDefaults(
  defineProps<{
    variant?: 'primary' | 'secondary' | 'ghost'
    type?: 'button' | 'submit' | 'reset'
    disabled?: boolean
    block?: boolean
  }>(),
  {
    variant: 'primary',
    type: 'button',
    disabled: false,
    block: false,
  },
)

const emit = defineEmits<{
  click: [event: MouseEvent]
}>()

const ripples = ref<Array<{ id: number; x: number; y: number }>>([])
let rippleId = 0

function onClick(event: MouseEvent) {
  if (event.currentTarget instanceof HTMLElement) {
    const rect = event.currentTarget.getBoundingClientRect()
    const id = ++rippleId
    ripples.value.push({
      id,
      x: event.clientX - rect.left,
      y: event.clientY - rect.top,
    })
    window.setTimeout(() => {
      ripples.value = ripples.value.filter((r) => r.id !== id)
    }, 520)
  }
  emit('click', event)
}
</script>

<template>
  <button
    :type="type"
    :disabled="disabled"
    class="game-button"
    :class="[
      `game-button--${variant}`,
      { 'game-button--block': block, 'game-button--disabled': disabled },
    ]"
    @click="onClick"
  >
    <span
      v-for="ripple in ripples"
      :key="ripple.id"
      class="game-button__ripple"
      :style="{ left: `${ripple.x}px`, top: `${ripple.y}px` }"
    />
    <span class="game-button__label">
      <slot />
    </span>
  </button>
</template>

<style scoped>
.game-button {
  position: relative;
  overflow: hidden;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.625rem 1.25rem;
  border-radius: var(--radius-button);
  font-size: 0.875rem;
  font-weight: 600;
  line-height: 1.25rem;
  border: 1px solid transparent;
  cursor: pointer;
  transition:
    transform var(--motion-duration) var(--motion-ease),
    box-shadow var(--motion-duration) var(--motion-ease),
    background-color var(--motion-duration) var(--motion-ease),
    border-color var(--motion-duration) var(--motion-ease);
}

.game-button:hover:not(:disabled) {
  transform: scale(1.02);
}

.game-button:active:not(:disabled) {
  transform: scale(0.98);
}

.game-button--block {
  width: 100%;
}

.game-button--disabled,
.game-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.game-button--primary {
  background: var(--color-accent);
  color: var(--color-bg);
  box-shadow: 0 4px 14px color-mix(in srgb, var(--color-accent) 35%, transparent);
}

.game-button--primary:hover:not(:disabled) {
  background: var(--color-accent-muted);
  box-shadow: 0 6px 20px color-mix(in srgb, var(--color-accent) 45%, transparent);
}

.game-button--secondary {
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
  border-color: var(--color-border);
}

.game-button--secondary:hover:not(:disabled) {
  background: var(--color-bg-elevated-2);
}

.game-button--ghost {
  background: transparent;
  color: var(--color-text-secondary);
  border-color: transparent;
}

.game-button--ghost:hover:not(:disabled) {
  color: var(--color-text-primary);
  background: var(--color-bg-elevated);
  border-color: var(--color-border);
}

.game-button__label {
  position: relative;
  z-index: 1;
}

.game-button__ripple {
  position: absolute;
  width: 8px;
  height: 8px;
  margin-left: -4px;
  margin-top: -4px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.45);
  pointer-events: none;
  animation: ripple 520ms var(--motion-ease) forwards;
  z-index: 0;
}
</style>
