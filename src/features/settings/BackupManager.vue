<script setup lang="ts">
import { onMounted, ref } from 'vue'

import GameButton from '@/shared/components/GameButton.vue'
import { createBackup, listBackups, restoreBackup } from '@/shared/api/settings'
import { useSettingsStore } from '@/stores/settings'
import { formatApiError } from '@/shared/utils/apiError'

const settings = useSettingsStore()
settings.load()

const backups = ref<string[]>([])
const loading = ref(true)
const working = ref(false)
const message = ref<string | null>(null)
const error = ref<string | null>(null)

const isTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window

async function refresh() {
  loading.value = true
  error.value = null
  try {
    backups.value = await listBackups()
  } catch (err) {
    error.value = formatApiError(err, '加载备份列表失败')
  } finally {
    loading.value = false
  }
}

async function onCreateBackup() {
  working.value = true
  message.value = null
  error.value = null
  try {
    const filename = await createBackup()
    message.value = `已创建备份：${filename}`
    await refresh()
  } catch (err) {
    error.value = formatApiError(err, '备份失败')
  } finally {
    working.value = false
  }
}

async function onRestore(filename: string) {
  if (!window.confirm(`确定用备份「${filename}」覆盖当前数据吗？应用将需要重启后完全生效。`)) return
  working.value = true
  message.value = null
  error.value = null
  try {
    await restoreBackup(filename)
    message.value = '恢复完成，建议重启夜记以确保数据一致'
  } catch (err) {
    error.value = formatApiError(err, '恢复失败')
  } finally {
    working.value = false
  }
}

onMounted(() => {
  void refresh()
})
</script>

<template>
  <div class="backup-manager">
    <p v-if="!isTauri" class="backup-manager__hint">备份与恢复功能仅在 Tauri 桌面应用中可用。</p>
    <template v-else>
      <label class="backup-manager__toggle">
        <input v-model="settings.autoBackup" type="checkbox" />
        <span>退出应用时自动备份</span>
      </label>
      <GameButton variant="secondary" :disabled="working" @click="onCreateBackup">
        {{ working ? '处理中…' : '立即备份' }}
      </GameButton>
      <p v-if="message" class="backup-manager__msg backup-manager__msg--ok">{{ message }}</p>
      <p v-if="error" class="backup-manager__msg backup-manager__msg--err">{{ error }}</p>
      <div class="backup-manager__list">
        <p v-if="loading" class="backup-manager__hint">加载备份列表…</p>
        <p v-else-if="backups.length === 0" class="backup-manager__hint">暂无备份文件</p>
        <ul v-else>
          <li v-for="name in backups" :key="name">
            <span>{{ name }}</span>
            <GameButton variant="ghost" :disabled="working" @click="onRestore(name)">恢复</GameButton>
          </li>
        </ul>
      </div>
    </template>
  </div>
</template>

<style scoped>
.backup-manager {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.backup-manager__hint {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
}

.backup-manager__toggle {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
}

.backup-manager__msg {
  font-size: 0.8125rem;
}

.backup-manager__msg--ok {
  color: var(--color-success);
}

.backup-manager__msg--err {
  color: var(--color-danger);
}

.backup-manager__list ul {
  list-style: none;
  padding: 0;
  margin: 0;
}

.backup-manager__list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--color-border);
  font-size: 0.8125rem;
  color: var(--color-text-primary);
}

.backup-manager__list li:last-child {
  border-bottom: none;
}
</style>
