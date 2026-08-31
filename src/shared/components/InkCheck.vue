<script setup lang="ts">
/**
 * InkCheck — 手绘勾（规格 §7.2-2）：SVG stroke-dashoffset 画勾，220ms 档。
 * 划线跟随由消费方对标题加 ink-strike 类实现。
 * reduced-motion 下瞬移（§7.3）。
 */
withDefaults(
  defineProps<{
    checked: boolean
    label?: string
  }>(),
  { label: '完成' },
)

const emit = defineEmits<{ toggle: [] }>()
</script>

<template>
  <button
    type="button"
    data-testid="ink-check"
    class="ink-check"
    :class="{ 'ink-check--done': checked }"
    :aria-label="label"
    :aria-pressed="checked"
    @click="emit('toggle')"
  >
    <svg viewBox="0 0 20 20" aria-hidden="true" class="ink-check__svg">
      <path
        class="ink-check__stroke"
        d="M4.5 10.8 C6.5 12.2, 7.8 13.4, 9.2 15 C10.8 11.6, 13.2 7.4, 16.2 4.8"
        pathLength="1"
        stroke-dasharray="1"
        :stroke-dashoffset="checked ? 0 : 1"
      />
    </svg>
  </button>
</template>

<style scoped>
.ink-check {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.375rem;
  height: 1.375rem;
  padding: 0;
  border: 1px solid var(--color-line);
  border-radius: 3px;
  background: transparent;
  cursor: pointer;
  transition: border-color var(--dur-fast) var(--ease-out-quart);
}

.ink-check:hover:not(:disabled) {
  border-color: var(--color-accent);
}

.ink-check--done {
  border-color: var(--color-accent);
}

.ink-check__svg {
  width: 0.875rem;
  height: 0.875rem;
  overflow: visible;
}

.ink-check__stroke {
  fill: none;
  stroke: var(--color-accent);
  stroke-width: 2;
  stroke-linecap: round;
  transition: stroke-dashoffset var(--dur-fast) var(--ease-out-quart);
}

@media (prefers-reduced-motion: reduce) {
  .ink-check,
  .ink-check__stroke {
    transition: none;
  }
}
</style>
