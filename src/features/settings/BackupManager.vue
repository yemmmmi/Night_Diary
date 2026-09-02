<script setup lang="ts">
import { onMounted, ref } from 'vue'

import GameButton from '@/shared/components/GameButton.vue'
import { createBackup, listBackups, restoreBackup } from '@/shared/api/settings'
import { exportAll, importJson, type ExportSummary } from '@/shared/api/export'
import { useSettingsStore } from '@/stores/settings'
import { formatApiError } from '@/shared/utils/apiError'
import { toIsoDate } from '@/shared/utils/diaryFormat'

const settings = useSettingsStore()
settings.load()

const backups = ref<string[]>([])
const loading = ref(true)
const working = ref(false)
const message = ref<string | null>(null)
const error = ref<string | null>(null)

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

async function onExportJson() {
  working.value = true
  message.value = null
  error.value = null
  try {
    const data = await exportAll()
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const date = toIsoDate(new Date())
    a.download = `nightdiary-export-${date}.json`
    a.click()
    URL.revokeObjectURL(url)
    message.value = `已导出 ${(data as { diaries?: unknown[] }).diaries?.length ?? 0} 篇日记`
  } catch (err) {
    error.value = formatApiError(err, '导出失败')
  } finally {
    working.value = false
  }
}

async function onImportJson(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  if (!window.confirm('导入将覆盖当前所有数据（日记、标签、记忆等），确定继续吗？')) {
    input.value = ''
    return
  }

  working.value = true
  message.value = null
  error.value = null
  try {
    const text = await file.text()
    const data = JSON.parse(text)
    const summary: ExportSummary = await importJson(data)
    message.value = `导入完成：${summary.diaries} 篇日记、${summary.tags} 个标签、${summary.memory_cards} 张记忆卡片`
    await refresh()
  } catch (err) {
    error.value = formatApiError(err, '导入失败，请检查文件格式')
  } finally {
    working.value = false
    input.value = ''
  }
}

function onToggleAutoBackup() {
  settings.autoBackup = !settings.autoBackup
}

onMounted(() => {
  void refresh()
})
</script>

<template>
  <div class="backup-manager">
    <!-- Auto backup toggle -->
    <div class="backup-manager__toggle">
      <button
        class="backup-manager__switch"
        :class="{ 'backup-manager__switch--on': settings.autoBackup }"
        :aria-pressed="settings.autoBackup"
        @click="onToggleAutoBackup"
      >
        <span class="backup-manager__switch-knob" />
      </button>
      <span>退出应用时自动备份</span>
    </div>

    <!-- Backup & restore -->
    <p class="backup-manager__hint">退出应用时会自动备份数据库（文件名以 <code>-auto.db</code> 结尾）。最多保留 20 份备份。</p>
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

    <!-- JSON export/import (always available) -->
    <div class="backup-manager__divider" />
    <p class="backup-manager__hint">导出所有数据为 JSON 文件，可用于跨设备迁移或数据备份。</p>
    <div class="backup-manager__actions">
      <GameButton variant="secondary" :disabled="working" @click="onExportJson">
        {{ working ? '处理中…' : '导出 JSON' }}
      </GameButton>
      <label class="backup-manager__file-label">
        <GameButton variant="ghost" :disabled="working" tag="span">导入 JSON</GameButton>
        <input
          type="file"
          accept=".json,application/json"
          class="backup-manager__file-input"
          :disabled="working"
          @change="onImportJson"
        />
      </label>
    </div>
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

.backup-manager__switch {
  position: relative;
  width: 2.5rem;
  height: 1.375rem;
  border: 1px solid var(--color-line);
  border-radius: var(--radius-button);
  background: transparent;
  cursor: pointer;
  transition:
    background var(--dur-fast) var(--ease-out-quart),
    border-color var(--dur-fast) var(--ease-out-quart);
  flex-shrink: 0;
  padding: 0;
}

.backup-manager__switch--on {
  border-color: var(--color-accent);
  background: var(--color-accent);
}

.backup-manager__switch-knob {
  position: absolute;
  top: 0.125rem;
  left: 0.125rem;
  width: 1rem;
  height: 1rem;
  border-radius: var(--radius-seal);
  background: var(--color-surface-raised);
  transition: transform var(--dur-fast) var(--ease-out-quart);
}

.backup-manager__switch--on .backup-manager__switch-knob {
  transform: translateX(1.0625rem);
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
  border-bottom: 1px solid var(--color-line);
  font-size: 0.8125rem;
  color: var(--color-text-primary);
}

.backup-manager__list li:last-child {
  border-bottom: none;
}

.backup-manager__divider {
  height: 1px;
  background: var(--color-line);
  margin: 0.5rem 0;
}

.backup-manager__actions {
  display: flex;
  gap: 0.75rem;
  align-items: center;
}

.backup-manager__file-label {
  position: relative;
  cursor: pointer;
}

.backup-manager__file-input {
  position: absolute;
  width: 0;
  height: 0;
  opacity: 0;
  overflow: hidden;
}
</style>
