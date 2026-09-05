<script setup lang="ts">
import { ref } from 'vue'

import GameButton from '@/shared/components/GameButton.vue'
import { exportAll, importJson, type ExportSummary } from '@/shared/api/export'
import { formatApiError } from '@/shared/utils/apiError'
import { toIsoDate } from '@/shared/utils/diaryFormat'

const working = ref(false)
const message = ref<string | null>(null)
const error = ref<string | null>(null)

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
  } catch (err) {
    error.value = formatApiError(err, '导入失败，请检查文件格式')
  } finally {
    working.value = false
    input.value = ''
  }
}
</script>

<template>
  <div class="backup-manager">
    <p class="backup-manager__hint">导出所有数据为 JSON 文件，可用于跨设备迁移或数据备份。</p>
    <p v-if="message" class="backup-manager__msg backup-manager__msg--ok">{{ message }}</p>
    <p v-if="error" class="backup-manager__msg backup-manager__msg--err">{{ error }}</p>
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

.backup-manager__msg {
  font-size: 0.8125rem;
}

.backup-manager__msg--ok {
  color: var(--color-success);
}

.backup-manager__msg--err {
  color: var(--color-danger);
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
