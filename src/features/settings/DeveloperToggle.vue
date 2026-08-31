<script setup lang="ts">
import { useSettingsStore } from '@/stores/settings'

const settings = useSettingsStore()
</script>

<template>
  <label class="settings-field settings-field--checkbox">
    <input v-model="settings.developerMode" type="checkbox" />
    <span>开发者模式</span>
    <span class="developer-toggle__hint">开启后显示数据链路追踪面板</span>
  </label>
</template>

<style scoped>
label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
}

.developer-toggle__hint {
  font-size: 0.7rem;
  color: var(--color-text-faint);
  margin-left: 0.5rem;
}

input {
  accent-color: var(--color-accent);
}
</style>
