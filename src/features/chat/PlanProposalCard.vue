<template>
  <div
    class="plan-proposal-card"
    :class="{
      accepted: status === 'accepted',
      rejected: status === 'rejected',
    }"
  >
    <div class="card-header">
      <span class="card-icon">📋</span>
      <span class="card-title">{{ proposal.title }}</span>
    </div>

    <p v-if="proposal.motivation" class="motivation">{{ proposal.motivation }}</p>

    <div v-if="proposal.source_refs?.length" class="source-refs">
      <span class="refs-label">参考来源：</span>
      <span
        v-for="ref in proposal.source_refs"
        :key="`${ref.type}-${ref.id}`"
        class="ref-chip"
      >
        {{ ref.type === 'diary' ? '日记' : ref.type === 'episodic' ? '记忆' : '资料' }}
        <span v-if="ref.date">{{ ref.date }}</span>
      </span>
    </div>

    <ul class="task-list">
      <li v-for="(task, i) in proposal.tasks" :key="i" class="task-item">
        <span class="task-title">{{ task.title }}</span>
        <span v-if="task.due_date" class="task-due">{{ task.due_date }}</span>
      </li>
    </ul>

    <div v-if="status === 'pending'" class="actions">
      <button class="btn-accept" @click="onAccept">采纳</button>
      <button class="btn-reject" @click="onReject">跳过</button>
    </div>
    <div v-else-if="status === 'accepted'" class="status-badge accepted">
      已添加到计划
    </div>
    <div v-else class="status-badge rejected">已跳过</div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { createPlan, type SourceRef } from '@/shared/api/plan'

interface ProposalData {
  title: string
  motivation?: string
  source_refs?: Array<{ type: string; id: string | number; date?: string }>
  tasks: Array<{ title: string; note?: string; due_date?: string }>
}

const props = defineProps<{
  proposal: ProposalData
  conversationId?: string
}>()

const emit = defineEmits<{ accepted: []; rejected: [] }>()
const status = ref<'pending' | 'accepted' | 'rejected'>('pending')

async function onAccept() {
  try {
    await createPlan({
      title: props.proposal.title,
      motivation: props.proposal.motivation,
      source_refs: props.proposal.source_refs?.map((r) => ({
        type: r.type as SourceRef['type'],
        id: r.id,
        date: r.date,
      })),
      tasks: props.proposal.tasks.map((t) => ({
        title: t.title,
        note: t.note,
        due_date: t.due_date,
      })),
      source: 'agent',
      created_from_conversation_id: props.conversationId,
    })
    status.value = 'accepted'
    emit('accepted')
  } catch {
    status.value = 'pending'
  }
}

function onReject() {
  status.value = 'rejected'
  emit('rejected')
}
</script>

<style scoped>
.plan-proposal-card {
  border: 1px solid var(--color-border, #e4e4e7);
  border-radius: 12px;
  padding: 16px;
  margin: 8px 0;
  background: var(--color-bg-elevated-2, #f9fafb);
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.card-title {
  font-weight: 600;
  font-size: 15px;
  color: var(--color-text-primary);
}

.motivation {
  font-size: 14px;
  color: var(--color-text-secondary, #52525b);
  margin: 8px 0;
  line-height: 1.5;
}

.source-refs {
  font-size: 12px;
  color: var(--color-text-secondary, #71717a);
  margin: 8px 0;
}

.ref-chip {
  display: inline-block;
  padding: 2px 8px;
  background: color-mix(in srgb, var(--color-accent) 15%, transparent);
  color: var(--color-accent);
  border-radius: 999px;
  margin-right: 4px;
}

.task-list {
  list-style: none;
  padding: 0;
  margin: 12px 0;
}

.task-item {
  padding: 6px 0;
  border-bottom: 1px dashed var(--color-border, #e4e4e7);
  font-size: 14px;
  color: var(--color-text-primary);
}

.task-due {
  float: right;
  color: var(--color-text-secondary, #71717a);
  font-size: 12px;
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
