<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { listTraces, getTrace, getDevStats, getMiddlewareStatus, type TraceSummary, type PipelineTrace, type MiddlewareStatus as MiddlewareStatusData } from '@/shared/api/dev'
import TraceList from '@/features/dev/TraceList.vue'
import TraceWaterfall from '@/features/dev/TraceWaterfall.vue'
import MiddlewareStatus from '@/features/dev/MiddlewareStatus.vue'
import AccountSwitcher from '@/features/dev/AccountSwitcher.vue'

const traces = ref<TraceSummary[]>([])
const total = ref(0)
const selectedTrace = ref<PipelineTrace | null>(null)
const stats = ref<{ total_traces: number; by_scenario: Record<string, number>; avg_duration_ms: number; error_count: number } | null>(null)
const middleware = ref<MiddlewareStatusData | null>(null)
const loading = ref(false)

async function loadTraces() {
  loading.value = true
  try {
    const result = await listTraces({ page: 1, page_size: 20 })
    traces.value = result.items
    total.value = result.total
  } catch {
    traces.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

async function selectTrace(traceId: string) {
  try {
    selectedTrace.value = await getTrace(traceId)
  } catch {
    // ignore
  }
}

async function loadStats() {
  try {
    const [s, m] = await Promise.all([getDevStats(), getMiddlewareStatus()])
    stats.value = s
    middleware.value = m
  } catch {
    // ignore
  }
}

function reload() {
  selectedTrace.value = null
  loadTraces()
  loadStats()
}

onMounted(() => {
  loadTraces()
  loadStats()
})
</script>

<template>
  <div class="dev-scene">
    <div class="dev-scene__sidebar">
      <TraceList :traces="traces" :total="total" :loading="loading" @select="selectTrace" />
    </div>
    <div class="dev-scene__main">
      <div class="dev-scene__topbar">
        <AccountSwitcher @switched="reload" />
        <MiddlewareStatus v-if="middleware" :status="middleware" />
        <div v-if="stats" class="dev-scene__stats">
          <span>{{ stats.total_traces }} 条</span>
          <span v-if="stats.avg_duration_ms">平均 {{ stats.avg_duration_ms.toFixed(0) }}ms</span>
          <span v-if="stats.error_count > 0" class="dev-scene__errors">{{ stats.error_count }} 错误</span>
        </div>
      </div>
      <TraceWaterfall v-if="selectedTrace" :trace="selectedTrace" />
      <div v-else class="dev-scene__empty">
        <p>选择一条记录查看详情</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dev-scene {
  display: grid;
  grid-template-columns: 18rem 1fr;
  height: calc(100dvh - 5rem);
  overflow: hidden;
}
.dev-scene__sidebar {
  border-right: 1px solid var(--color-border);
  overflow-y: auto;
  background: var(--color-bg-elevated);
}
.dev-scene__main {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.dev-scene__topbar {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.5rem 1rem;
  border-bottom: 1px solid var(--color-border);
  font-size: 0.75rem;
}
.dev-scene__stats {
  display: flex;
  gap: 1rem;
  margin-left: auto;
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: var(--color-text-secondary);
}
.dev-scene__errors {
  color: var(--color-danger);
}
.dev-scene__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  color: var(--color-text-secondary);
  font-size: 0.875rem;
}
</style>
