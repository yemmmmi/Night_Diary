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
    <div class="theme-toggle__options" role="radiogroup" aria-label="主题偏好">
      <button
        v-for="option in options"
        :key="option.value"
        type="button"
        role="radio"
        :aria-checked="preference === option.value"
        class="theme-toggle__option"
        :class="{ 'is-active': preference === option.value }"
        @click="preference = option.value"
      >
        <component :is="option.icon" :size="16" weight="duotone" />
        {{ option.label }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.theme-toggle {
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}

.theme-toggle__hint {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
}

.theme-toggle__options {
  display: flex;
  flex-wrap: wrap;
  gap: 0.125rem 1.375rem;
}

/* 纸感文字选项：无底无框，选中以一道 accent 底线示意。 */
.theme-toggle__option {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.375rem 0.125rem;
  border: none;
  border-bottom: 2px solid transparent;
  border-radius: 0;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 0.8125rem;
  cursor: pointer;
  transition:
    color var(--dur-fast) var(--ease-out-quart),
    border-color var(--dur-fast) var(--ease-out-quart);
}

.theme-toggle__option:hover {
  color: var(--color-text-primary);
}

.theme-toggle__option.is-active {
  color: var(--color-text-primary);
  border-bottom-color: var(--color-accent);
}
</style>
