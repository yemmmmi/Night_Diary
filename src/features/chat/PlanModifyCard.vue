<template>
  <div
    class="plan-modify-card"
    :class="{
      accepted: status === 'accepted',
      rejected: status === 'rejected',
    }"
  >
    <div class="card-header">
      <span class="card-icon">✏️</span>
      <span class="card-kind">{{ operationLabel }}</span>
      <span class="card-target">{{ proposal.target.title }}</span>
    </div>

    <p v-if="proposal.reason" class="reason">{{ proposal.reason }}</p>

    <div class="change-list" v-if="changeLines.length">
      <div v-for="(line, i) in changeLines" :key="i" class="change-line">
        <span class="change-dot" />{{ line }}
      </div>
    </div>

    <div v-if="status === 'pending'" class="actions">
      <button class="btn-accept" :disabled="busy" @click="onAccept">采纳</button>
      <button class="btn-reject" :disabled="busy" @click="onReject">跳过</button>
    </div>
    <div v-else-if="status === 'accepted'" class="status-badge accepted">已应用</div>
    <div v-else class="status-badge rejected">已跳过</div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  archiveTask,
  deletePlan,
  deleteTask,
  updatePlan,
  updateTask,
} from '@/shared/api/plan'

interface ModifyTarget {
  type: 'plan' | 'task'
  id: string
  title: string
}

interface ModifyData {
  operation: 'adjust' | 'archive' | 'clean'
  target: ModifyTarget
  changes: Record<string, string>
  reason?: string
}

const props = defineProps<{
  proposal: ModifyData
}>()

const emit = defineEmits<{ accepted: []; rejected: [] }>()
const status = ref<'pending' | 'accepted' | 'rejected'>('pending')
const busy = ref(false)

const OPERATION_LABELS: Record<ModifyData['operation'], string> = {
  adjust: '调整',
  archive: '归档',
  clean: '清理',
}

const operationLabel = computed(() => OPERATION_LABELS[props.proposal.operation] ?? '修改')

// 把 changes 的键翻译成人类可读的一行行描述
function describeChanges(changes: Record<string, string>): string[] {
  const KEY_LABELS: Record<string, string> = {
    title: '标题',
    motivation: '动机',
    note: '备注',
    due_date: '截止日期',
    status: '状态',
  }
  return Object.entries(changes).map(([k, v]) => {
    const label = KEY_LABELS[k] ?? k
    return `${label} → ${v || '（清除）'}`
  })
}

const changeLines = computed(() => describeChanges(props.proposal.changes ?? {}))

async function onAccept() {
  busy.value = true
  try {
    const { operation, target, changes } = props.proposal
    if (operation === 'clean') {
      // 清理 = 删除目标
      if (target.type === 'plan') await deletePlan(target.id)
      else await deleteTask(target.id)
    } else if (operation === 'archive') {
      // 归档：计划 -> archived；任务 -> skipped（任务无 archived 态）
      if (target.type === 'plan') await updatePlan(target.id, { status: 'archived' })
      else await archiveTask(target.id)
    } else {
      // adjust：PATCH 对应对象，仅透传后端已知字段
      if (target.type === 'task') {
        const picked: Partial<Record<'title' | 'note' | 'due_date', string>> = {}
        if ('title' in changes) picked.title = String(changes.title)
        if ('note' in changes) picked.note = String(changes.note)
        if ('due_date' in changes) picked.due_date = String(changes.due_date)
        await updateTask(target.id, picked as never)
      } else {
        const picked: Partial<Record<'title' | 'motivation' | 'status', string>> = {}
        if ('title' in changes) picked.title = String(changes.title)
        if ('motivation' in changes) picked.motivation = String(changes.motivation)
        if ('status' in changes) picked.status = String(changes.status)
        await updatePlan(target.id, picked as never)
      }
    }
    status.value = 'accepted'
    emit('accepted')
  } catch {
    status.value = 'pending'
  } finally {
    busy.value = false
  }
}

function onReject() {
  status.value = 'rejected'
  emit('rejected')
}
</script>

<style scoped>
.plan-modify-card {
  border: 1px solid var(--color-border, #e4e4e7);
  border-radius: 12px;
  padding: 14px 16px;
  margin: 8px 0;
  background: var(--color-bg-elevated-2, #f9fafb);
  font-size: 14px;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.card-kind {
  background: color-mix(in srgb, var(--color-accent) 14%, transparent);
  color: var(--color-accent);
  border-radius: 999px;
  padding: 2px 10px;
  font-size: 12px;
  font-weight: 600;
}

.card-target {
  font-weight: 600;
  color: var(--color-text-primary);
}

.reason {
  font-size: 13px;
  color: var(--color-text-secondary, #52525b);
  margin: 6px 0;
  line-height: 1.5;
}

.change-list {
  margin: 8px 0;
}

.change-line {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  color: var(--color-text-primary);
}

.change-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-accent-muted, #a1a1aa);
  flex: none;
}

.actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}

.btn-accept {
  background: var(--color-accent);
  color: white;
  border: none;
  padding: 6px 16px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
}

.btn-reject {
  background: transparent;
  color: var(--color-text-secondary, #71717a);
  border: 1px solid var(--color-border, #e4e4e7);
  padding: 6px 16px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
}

.btn-accept:disabled,
.btn-reject:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.status-badge {
  font-size: 13px;
  padding: 4px 0;
  margin-top: 4px;
}

.status-badge.accepted {
  color: #10b981;
}

.status-badge.rejected {
  color: var(--color-text-secondary, #71717a);
}
</style>
