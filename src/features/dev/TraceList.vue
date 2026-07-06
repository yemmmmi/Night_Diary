<script setup lang="ts">
import type { TraceSummary } from '@/shared/api/dev'

defineProps<{
  traces: TraceSummary[]
  total: number
  loading: boolean
}>()

const emit = defineEmits<{
  select: [traceId: string]
}>()

function scenarioLabel(scenario: string): string {
  return scenario === 'diary' || scenario === 'diary_reply' ? '日记' : '会话'
}

function statusColor(status: string): string {
  if (status === 'error') return 'var(--color-danger)'
  if (status === 'completed') return 'var(--color-success)'
  return 'var(--color-text-secondary)'
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${hh}:${mm}`
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms.toFixed(0)}ms`
  return `${(ms / 1000).toFixed(2)}s`
}

function onSelect(traceId: string) {
  emit('select', traceId)
}
</script>

<template>
  <div class="trace-list">
    <div class="trace-list__header">
      <span class="trace-list__title">追踪记录</span>
      <span v-if="total > 0" class="trace-list__count">{{ total }}</span>
    </div>

    <div v-if="loading" class="trace-list__empty">加载中...</div>
    <div v-else-if="traces.length === 0" class="trace-list__empty">暂无记录</div>

    <div v-else class="trace-list__items">
      <button
        v-for="trace in traces"
        :key="trace.trace_id"
        class="trace-list__item"
        @click="onSelect(trace.trace_id)"
      >
        <span class="trace-list__dot" :style="{ background: statusColor(trace.status) }" />
        <div class="trace-list__info">
          <div class="trace-list__row">
            <span class="trace-list__scenario">{{ scenarioLabel(trace.scenario) }}</span>
            <span class="trace-list__time">{{ formatTime(trace.started_at) }}</span>
          </div>
          <div class="trace-list__row">
            <span class="trace-list__spans">{{ trace.span_count }} stages</span>
            <span class="trace-list__duration">{{ formatDuration(trace.duration_ms) }}</span>
          </div>
        </div>
      </button>
    </div>
  </div>
</template>

<style scoped>
.trace-list {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.trace-list__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.625rem 0.875rem;
  border-bottom: 1px solid var(--color-border);
}
.trace-list__title {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--color-text-primary);
}
.trace-list__count {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: var(--color-text-secondary);
}
.trace-list__empty {
  padding: 2rem 1rem;
  text-align: center;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}
.trace-list__items {
  flex: 1;
  overflow-y: auto;
}
.trace-list__item {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  width: 100%;
  padding: 0.5rem 0.75rem;
  border: none;
  border-bottom: 1px solid var(--color-border);
  background: transparent;
  cursor: pointer;
  text-align: left;
  transition: background var(--motion-duration) var(--motion-ease);
}
.trace-list__item:hover {
  background: var(--color-bg-elevated);
}
.trace-list__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-top: 0.25rem;
  flex-shrink: 0;
}
.trace-list__info {
  flex: 1;
  min-width: 0;
}
.trace-list__row {
  display: flex;
  justify-content: space-between;
  font-size: 0.7rem;
  color: var(--color-text-secondary);
  font-family: var(--font-mono);
}
.trace-list__row + .trace-list__row {
  margin-top: 0.125rem;
}
.trace-list__scenario {
  font-family: var(--font-ui);
  font-size: 0.75rem;
  color: var(--color-text-primary);
  font-weight: 500;
}
</style>
