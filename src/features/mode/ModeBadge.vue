<script setup lang="ts">
import { ref } from 'vue'
import { getCurrentMode, overrideMode, type UserMode } from '@/shared/api/mode'

defineOptions({ name: 'ModeBadge' })

const modeOptions: Array<{ value: UserMode; label: string; hint: string }> = [
  { value: 'daily', label: '日常', hint: '帮你记录、规划、复盘，推进但不催促' },
  { value: 'followup', label: '跟进', hint: '你愿意时，带你往前带一两步，不勉强' },
  { value: 'introspection', label: '内视', hint: '今天先从内里看看此刻的自己，暂缓计划推进' },
]

const currentMode = ref<UserMode>('daily')
const open = ref(false)
const hidden = ref(false)

async function load() {
  try {
    const { mode } = await getCurrentMode()
    currentMode.value = mode
  } catch {
    // keep daily default on failure
  }
}

async function choose(value: UserMode) {
  currentMode.value = value
  open.value = false
  try {
    const { mode } = await overrideMode(value)
    currentMode.value = mode
  } catch {
    // local selection stands even if the API fails
  }
}

const current = (modeOptions.find((m) => m.value === currentMode.value) ?? modeOptions[0])

defineExpose({ load })
</script>

<template>
  <div v-if="!hidden" class="mode-badge">
    <button
      type="button"
      class="mode-badge__trigger"
      :title="current.hint"
      @click="open = !open"
    >
      <span class="mode-badge__dot" />
      {{ current.label }}
    </button>

    <div v-if="open" class="mode-badge__panel">
      <p class="mode-badge__title">当前模式</p>
      <button
        v-for="opt in modeOptions"
        :key="opt.value"
        type="button"
        class="mode-badge__option"
        :class="{ 'mode-badge__option--active': opt.value === currentMode }"
        @click="choose(opt.value)"
      >
        <span class="mode-badge__option-label">{{ opt.label }}</span>
        <span class="mode-badge__option-hint">{{ opt.hint }}</span>
      </button>
      <button type="button" class="mode-badge__hide" @click="hidden = true">隐藏此徽标</button>
    </div>
  </div>
</template>

<style scoped>
.mode-badge {
  position: relative;
  font-size: 0.75rem;
}

.mode-badge__trigger {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.3125rem 0.625rem;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
  cursor: pointer;
  transition:
    border-color var(--motion-duration) var(--motion-ease),
    color var(--motion-duration) var(--motion-ease);
}

.mode-badge__trigger:hover {
  border-color: var(--color-accent-muted);
}

.mode-badge__dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  background: var(--color-accent);
}

.mode-badge__panel {
  position: absolute;
  right: 0;
  top: calc(100% + 0.375rem);
  width: 16rem;
  padding: 0.625rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-outer);
  background: var(--color-bg-elevated);
  box-shadow: 0 0.5rem 1.5rem rgba(0, 0, 0, 0.12);
  z-index: 60;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.mode-badge__title {
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
  margin: 0 0 0.25rem;
}

.mode-badge__option {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.125rem;
  padding: 0.4375rem 0.5625rem;
  border: 1px solid transparent;
  border-radius: 0.5rem;
  background: transparent;
  cursor: pointer;
  text-align: left;
}

.mode-badge__option--active {
  border-color: var(--color-accent-muted);
  background: var(--color-bg-elevated-2);
}

.mode-badge__option-label {
  font-size: 0.8125rem;
  color: var(--color-text-primary);
  font-weight: 600;
}

.mode-badge__option-hint {
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
}

.mode-badge__hide {
  margin-top: 0.25rem;
  padding: 0.25rem;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 0.6875rem;
  cursor: pointer;
  align-self: flex-start;
}
</style>
