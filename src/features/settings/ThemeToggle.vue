<script setup lang="ts">
import { PhMoon, PhSun, PhMonitor } from '@phosphor-icons/vue'

import { useTheme, type ThemePreference } from '@/shared/composables/useTheme'

const { preference, theme } = useTheme()

const options: { value: ThemePreference; label: string; icon: typeof PhSun }[] = [
  { value: 'day', label: '白天', icon: PhSun },
  { value: 'night', label: '夜间', icon: PhMoon },
  { value: 'auto', label: '跟随系统', icon: PhMonitor },
]
</script>

<template>
  <div class="theme-toggle">
    <p class="theme-toggle__hint">
      当前生效：<strong>{{ theme === 'day' ? '白天' : '夜间' }}</strong>
    </p>
    <div class="theme-toggle__options">
      <button
        v-for="option in options"
        :key="option.value"
        type="button"
        class="theme-toggle__option"
        :class="{ 'is-active': preference === option.value }"
        @click="preference = option.value"
      >
        <component :is="option.icon" :size="18" weight="duotone" />
        {{ option.label }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.theme-toggle {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.theme-toggle__hint {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
}

.theme-toggle__options {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.theme-toggle__option {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.5rem 0.875rem;
  border-radius: 999px;
  border: 1px solid var(--color-border);
  background: var(--color-surface-raised);
  color: var(--color-text-secondary);
  font-size: 0.8125rem;
  transition:
    border-color var(--motion-duration) var(--motion-ease),
    color var(--motion-duration) var(--motion-ease),
    background var(--motion-duration) var(--motion-ease);
}

.theme-toggle__option.is-active {
  border-color: color-mix(in srgb, var(--color-accent) 50%, var(--color-border));
  color: var(--color-text-primary);
  background: color-mix(in srgb, var(--color-accent) 12%, var(--color-surface-raised));
}
</style>
