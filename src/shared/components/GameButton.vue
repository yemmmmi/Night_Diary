<script setup lang="ts">
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
    @click="emit('click', $event)"
  >
    <span class="game-button__label">
      <slot />
    </span>
  </button>
</template>

<style scoped>
/* 墨块按压（规格 §7.2-3）：hover 上浮 1.5px、active 下沉 1px，150ms。 */
.game-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.375rem;
  padding: 0.375rem 0.875rem;
  border-radius: var(--radius-seal);
  font-size: 0.8125rem;
  font-weight: 600;
  line-height: 1.25rem;
  border: 1px solid transparent;
  cursor: pointer;
  transition:
    transform var(--dur-instant) var(--ease-out-quart),
    background-color var(--dur-fast) var(--ease-out-quart),
    border-color var(--dur-fast) var(--ease-out-quart),
    color var(--dur-fast) var(--ease-out-quart);
}

.game-button:hover:not(:disabled) {
  transform: translateY(-1.5px);
}

.game-button:active:not(:disabled) {
  transform: translateY(1px);
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
}

.game-button--primary:hover:not(:disabled) {
  background: var(--color-accent-muted);
}

.game-button--secondary {
  background: transparent;
  color: var(--color-text-secondary);
  border-color: var(--color-border);
}

.game-button--secondary:hover:not(:disabled) {
  color: var(--color-text-primary);
  background: var(--color-bg-elevated);
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

@media (prefers-reduced-motion: reduce) {
  .game-button {
    transition: none;
  }
}
</style>
