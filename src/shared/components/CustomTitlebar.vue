<script setup lang="ts">
import { getCurrentWindow } from '@tauri-apps/api/window'
import { PhMinus, PhSquare, PhX } from '@phosphor-icons/vue'

import BrandMark from '@/shared/components/BrandMark.vue'

async function minimize() {
  await getCurrentWindow().minimize()
}

async function toggleMaximize() {
  const win = getCurrentWindow()
  if (await win.isMaximized()) {
    await win.unmaximize()
  } else {
    await win.maximize()
  }
}

async function closeWindow() {
  await getCurrentWindow().close()
}
</script>

<template>
  <header class="titlebar glass-panel glass-panel--blur">
    <div class="titlebar__drag" data-tauri-drag-region>
      <BrandMark class="titlebar__logo" />
      <span class="titlebar__title" data-tauri-drag-region>夜记</span>
    </div>
    <div class="titlebar__controls">
      <button type="button" class="titlebar__btn" aria-label="最小化" @click="minimize">
        <PhMinus :size="14" weight="bold" />
      </button>
      <button type="button" class="titlebar__btn" aria-label="最大化" @click="toggleMaximize">
        <PhSquare :size="12" weight="bold" />
      </button>
      <button
        type="button"
        class="titlebar__btn titlebar__btn--close"
        aria-label="关闭"
        @click="closeWindow"
      >
        <PhX :size="14" weight="bold" />
      </button>
    </div>
  </header>
</template>

<style scoped>
.titlebar {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 2.5rem;
  padding: 0 0.5rem 0 0.75rem;
  border-radius: 0;
  border-top: none;
  border-left: none;
  border-right: none;
  background: var(--glass-bg);
  border-bottom: 1px solid var(--glass-border);
}

.titlebar__drag {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex: 1;
  min-width: 0;
  height: 100%;
}

.titlebar__logo {
  width: 1.25rem;
  height: 1.25rem;
  flex-shrink: 0;
}

.titlebar__title {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--color-text-primary);
  user-select: none;
}

.titlebar__controls {
  display: flex;
  align-items: center;
  gap: 0.125rem;
}

.titlebar__btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 1.75rem;
  border: none;
  border-radius: 0.375rem;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: background-color var(--motion-duration) var(--motion-ease);
}

.titlebar__btn:hover {
  background: var(--color-bg-elevated-2);
  color: var(--color-text-primary);
}

.titlebar__btn--close:hover {
  background: var(--color-danger);
  color: #fff;
}
</style>
