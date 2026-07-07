<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useDevStore } from '@/stores/dev'
import { useTraceStream } from '@/shared/composables/useTraceStream'
import TraceSpanRow from './TraceSpanRow.vue'

const devStore = useDevStore()
const { activeTraceId } = storeToRefs(devStore)
const { spans, status, traceInfo } = useTraceStream(activeTraceId)

const completedCount = computed(() => spans.value.filter(s => s.status === 'completed' || s.status === 'error' || s.status === 'dispatched').length)
const totalCount = computed(() => spans.value.length)
</script>

<template>
  <div class="dev-pipeline-panel">
    <div class="dev-pipeline-panel__header">
      <span class="dev-pipeline-panel__title">实时追踪</span>
      <span v-if="totalCount > 0" class="dev-pipeline-panel__progress">{{ completedCount }}/{{ totalCount }}</span>
    </div>

    <div v-if="status === 'connecting'" class="dev-pipeline-panel__status">连接中...</div>
    <div v-else-if="status === 'error'" class="dev-pipeline-panel__status dev-pipeline-panel__status--error">
      连接中断，完成后可查看回溯
    </div>
    <div v-else-if="status === 'idle'" class="dev-pipeline-panel__status dev-pipeline-panel__status--idle">
      等待操作...
    </div>

    <div class="dev-pipeline-panel__timeline">
      <TraceSpanRow v-for="span in spans" :key="span.span_id" :span="span" />
    </div>

    <div v-if="traceInfo" class="dev-pipeline-panel__footer">
      <span>总耗时 {{ traceInfo.duration_ms?.toFixed(0) }}ms</span>
      <span>{{ traceInfo.status }}</span>
    </div>
  </div>
</template>

<style scoped>
.dev-pipeline-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  font-family: var(--font-ui);
}
.dev-pipeline-panel__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid var(--color-border);
  font-size: 0.75rem;
}
.dev-pipeline-panel__title {
  font-weight: 600;
  color: var(--color-text-primary);
}
.dev-pipeline-panel__progress {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: var(--color-text-secondary);
}
.dev-pipeline-panel__status {
  padding: 0.5rem 0.75rem;
  font-size: 0.7rem;
  color: var(--color-text-secondary);
}
.dev-pipeline-panel__status--error { color: var(--color-danger); }
.dev-pipeline-panel__status--idle { opacity: 0.5; }
.dev-pipeline-panel__timeline {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}
.dev-pipeline-panel__footer {
  display: flex;
  justify-content: space-between;
  padding: 0.5rem 0.75rem;
  border-top: 1px solid var(--color-border);
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: var(--color-text-secondary);
}
</style>
