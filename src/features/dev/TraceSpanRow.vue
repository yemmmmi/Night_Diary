<script setup lang="ts">
import { ref } from 'vue'
import type { TraceSpan } from '@/shared/api/dev'

const props = defineProps<{
  span: TraceSpan
  depth?: number
}>()

const expanded = ref(false)

function statusColor(status: string): string {
  switch (status) {
    case 'running': return 'var(--color-accent)'
    case 'completed': return 'var(--color-success)'
    case 'error': return 'var(--color-danger)'
    case 'dispatched': return 'var(--color-text-secondary)'
    default: return 'var(--color-text-secondary)'
  }
}

function formatDuration(ms: number | null): string {
  if (ms === null) return '...'
  if (ms < 1) return '<1ms'
  if (ms < 1000) return `${ms.toFixed(1)}ms`
  return `${(ms / 1000).toFixed(2)}s`
}

function hasContent(obj: Record<string, unknown> | null | undefined): boolean {
  return !!obj && Object.keys(obj).length > 0
}

// 引用 props 避免未使用告警（depth 在模板中使用，props 在此处保留语义）
void props
</script>

<template>
  <div class="trace-span-row" :style="{ '--depth': depth ?? 0 }">
    <button class="trace-span-row__header" @click="expanded = !expanded">
      <span class="trace-span-row__dot" :style="{ background: statusColor(span.status) }" />
      <span class="trace-span-row__label">{{ span.stage_label || span.stage_name }}</span>
      <span class="trace-span-row__name">{{ span.stage_name }}</span>
      <span class="trace-span-row__duration">{{ formatDuration(span.duration_ms) }}</span>
      <span v-if="span.error" class="trace-span-row__error">!</span>
    </button>

    <div v-if="expanded" class="trace-span-row__detail">
      <div v-if="hasContent(span.input_snapshot)" class="trace-span-row__section">
        <span class="trace-span-row__section-label">输入</span>
        <pre class="trace-span-row__code">{{ JSON.stringify(span.input_snapshot, null, 2) }}</pre>
      </div>
      <div v-if="hasContent(span.output_snapshot)" class="trace-span-row__section">
        <span class="trace-span-row__section-label">输出</span>
        <pre class="trace-span-row__code">{{ JSON.stringify(span.output_snapshot, null, 2) }}</pre>
      </div>
      <div v-if="hasContent(span.metadata)" class="trace-span-row__section">
        <span class="trace-span-row__section-label">元数据</span>
        <pre class="trace-span-row__code">{{ JSON.stringify(span.metadata, null, 2) }}</pre>
      </div>
      <div v-if="span.error" class="trace-span-row__section trace-span-row__section--error">
        <span class="trace-span-row__section-label">错误</span>
        <pre class="trace-span-row__code">{{ span.error }}</pre>
      </div>
    </div>

    <div v-if="span.child_spans.length" class="trace-span-row__children">
      <TraceSpanRow v-for="child in span.child_spans" :key="child.span_id" :span="child" :depth="(depth ?? 0) + 1" />
    </div>
  </div>
</template>

<style scoped>
.trace-span-row {
  --indent: calc(var(--depth) * 16px);
}
.trace-span-row__header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  padding: 0.375rem 0.5rem 0.375rem calc(0.5rem + var(--indent));
  background: transparent;
  border: none;
  border-bottom: 1px solid var(--color-border);
  cursor: pointer;
  text-align: left;
  font-family: var(--font-ui);
  font-size: 0.75rem;
  color: var(--color-text-primary);
}
.trace-span-row__header:hover {
  background: var(--color-bg-elevated);
}
.trace-span-row__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  transition: background 200ms ease;
}
.trace-span-row__label {
  font-weight: 500;
}
.trace-span-row__name {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  opacity: 0.5;
}
.trace-span-row__duration {
  margin-left: auto;
  font-family: var(--font-mono);
  font-size: 0.7rem;
  opacity: 0.7;
}
.trace-span-row__error {
  color: var(--color-danger);
  font-weight: bold;
}
.trace-span-row__detail {
  padding: 0.5rem 0.5rem 0.5rem calc(0.5rem + var(--indent));
  border-bottom: 1px solid var(--color-border);
}
.trace-span-row__section {
  margin-bottom: 0.5rem;
}
.trace-span-row__section-label {
  display: block;
  font-size: 0.65rem;
  text-transform: uppercase;
  opacity: 0.5;
  margin-bottom: 0.25rem;
}
.trace-span-row__code {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  background: var(--color-bg-elevated);
  padding: 0.5rem;
  border-radius: 0.375rem;
  overflow-x: auto;
  margin: 0;
  color: var(--color-text-secondary);
  max-height: 200px;
  overflow-y: auto;
}
.trace-span-row__section--error .trace-span-row__code {
  color: var(--color-danger);
}
.trace-span-row__children {
  border-left: 2px solid var(--color-border);
  margin-left: calc(0.5rem + var(--indent));
}
</style>
