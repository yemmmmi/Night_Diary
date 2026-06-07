<script setup lang="ts">
withDefaults(
  defineProps<{
    label?: string
  }>(),
  {
    label: '正在思考…',
  },
)
</script>

<template>
  <div class="typing-indicator" role="status" aria-live="polite">
    <span class="typing-indicator__dots" aria-hidden="true">
      <span class="typing-indicator__dot" />
      <span class="typing-indicator__dot" />
      <span class="typing-indicator__dot" />
    </span>
    <span class="typing-indicator__label">{{ label }}</span>
  </div>
</template>

<style scoped>
.typing-indicator {
  display: inline-flex;
  align-items: center;
  gap: 0.75rem;
  color: var(--color-text-secondary);
  font-size: 0.875rem;
}

.typing-indicator__dots {
  display: inline-flex;
  gap: 0.35rem;
}

.typing-indicator__dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  background: var(--color-accent);
  animation: typing-pulse 1.2s ease-in-out infinite;
}

.typing-indicator__dot:nth-child(2) {
  animation-delay: 0.15s;
}

.typing-indicator__dot:nth-child(3) {
  animation-delay: 0.3s;
}

@keyframes typing-pulse {
  0%,
  80%,
  100% {
    opacity: 0.35;
    transform: scale(0.85);
  }
  40% {
    opacity: 1;
    transform: scale(1);
  }
}
</style>
