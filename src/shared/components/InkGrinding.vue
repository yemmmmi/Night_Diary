<script setup lang="ts">
/**
 * InkGrinding — 研墨（规格 §7.2-5）：墨点呼吸 + 墨晕扩散，2.2s 循环。
 * 用于加载与等待态。reduced-motion 下静止呈现（§7.3）。
 */
withDefaults(
  defineProps<{ size?: 'sm' | 'md' }>(),
  { size: 'sm' },
)
</script>

<template>
  <span
    data-testid="ink-grinding"
    class="ink-grinding"
    :class="`ink-grinding--${size}`"
    role="status"
    aria-label="研墨中"
  >
    <span class="ink-grinding__halo" aria-hidden="true" />
    <span class="ink-grinding__dot" aria-hidden="true" />
  </span>
</template>

<style scoped>
.ink-grinding {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.ink-grinding--sm {
  width: 1.25rem;
  height: 1.25rem;
}

.ink-grinding--md {
  width: 2rem;
  height: 2rem;
}

.ink-grinding__dot {
  width: 28%;
  height: 28%;
  border-radius: 50%;
  background: var(--color-text-secondary);
  animation: ink-dot-breathe 2.2s var(--ease-out-quart) infinite;
}

.ink-grinding__halo {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 1px solid var(--color-text-faint);
  animation: ink-halo-spread 2.2s var(--ease-out-quart) infinite;
}

@keyframes ink-dot-breathe {
  0%,
  100% {
    transform: scale(0.85);
    opacity: 0.7;
  }
  50% {
    transform: scale(1.1);
    opacity: 1;
  }
}

@keyframes ink-halo-spread {
  0% {
    transform: scale(0.5);
    opacity: 0.9;
  }
  70%,
  100% {
    transform: scale(1.05);
    opacity: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .ink-grinding__dot,
  .ink-grinding__halo {
    animation: none;
  }

  .ink-grinding__halo {
    opacity: 0;
  }
}
</style>
