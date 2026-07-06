<script setup lang="ts">
import type { PipelineTrace } from '@/shared/api/dev'
import TraceSpanRow from './TraceSpanRow.vue'

defineProps<{
  trace: PipelineTrace
}>()

function formatDuration(ms: number | null | undefined): string {
  if (!ms) return '-'
  if (ms < 1000) return `${ms.toFixed(0)}ms`
  return `${(ms / 1000).toFixed(2)}s`
}

function scenarioLabel(scenario: string): string {
  return scenario === 'diary' || scenario === 'diary_reply' ? '日记分析' : '会话对话'
}
</script>

<template>
  <div class="trace-waterfall">
    <div class="trace-waterfall__header">
      <div class="trace-waterfall__info">
        <span class="trace-waterfall__scenario">{{ scenarioLabel(trace.scenario) }}</span>
        <span class="trace-waterfall__status" :class="{ 'trace-waterfall__status--error': trace.status === 'error' }">
          {{ trace.status }}
        </span>
      </div>
      <div class="trace-waterfall__meta">
        <span>{{ trace.span_count }} stages</span>
        <span>{{ formatDuration(trace.duration_ms) }}</span>
      </div>
    </div>

    <div class="trace-waterfall__tree">
      <TraceSpanRow v-for="span in trace.spans" :key="span.span_id" :span="span" />
    </div>
  </div>
</template>

<style scoped>
.trace-waterfall {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}
.trace-waterfall__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.625rem 1rem;
  border-bottom: 1px solid var(--color-border);
}
.trace-waterfall__info {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.trace-waterfall__scenario {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-text-primary);
}
.trace-waterfall__status {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  padding: 0.125rem 0.375rem;
  border-radius: 0.25rem;
  background: var(--color-success);
  color: var(--color-bg);
}
.trace-waterfall__status--error {
  background: var(--color-danger);
}
.trace-waterfall__meta {
  display: flex;
  gap: 1rem;
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: var(--color-text-secondary);
}
.trace-waterfall__tree {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}
</style>
