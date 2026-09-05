<script setup lang="ts">
import { onMounted, ref } from 'vue'
import type { McpCallLog, McpEndpointStatus, McpToolInfo } from '@/shared/api/dev'
import { getMcpCalls, getMcpStatus, getMcpTools } from '@/shared/api/dev'

const emit = defineEmits<{ openTrace: [traceId: string] }>()

const endpoints = ref<McpEndpointStatus[]>([])
const tools = ref<McpToolInfo[]>([])
const calls = ref<McpCallLog[]>([])
const callsTotal = ref(0)
const loading = ref(false)
const statusFilter = ref('')
const expandedCallId = ref<string | null>(null)

async function load(): Promise<void> {
  loading.value = true
  try {
    const [status, toolList, callList] = await Promise.all([
      getMcpStatus(),
      getMcpTools(),
      getMcpCalls(statusFilter.value ? { status: statusFilter.value } : undefined),
    ])
    endpoints.value = status.items
    tools.value = toolList.items
    calls.value = callList.items
    callsTotal.value = callList.total
  } catch {
    endpoints.value = []
    tools.value = []
    calls.value = []
    callsTotal.value = 0
  } finally {
    loading.value = false
  }
}

function toggleCall(id: string): void {
  expandedCallId.value = expandedCallId.value === id ? null : id
}

function stateLabel(state: string): string {
  if (state === 'healthy') return '正常'
  if (state === 'dead') return '已停止'
  return '异常'
}

function formatDuration(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`
}

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleString()
}

onMounted(() => void load())
</script>

<template>
  <div class="mcp-panel">
    <div class="mcp-panel__header">
      <span class="mcp-panel__title">MCP 工具</span>
      <button class="mcp-panel__refresh" :disabled="loading" @click="load">刷新</button>
    </div>

    <section class="mcp-panel__section">
      <h3 class="mcp-panel__section-title">端点（{{ endpoints.length }}）</h3>
      <div v-if="endpoints.length === 0" class="mcp-panel__empty">
        未配置 MCP 端点（.env 中设置 MCP_ENDPOINTS / MCP_STDIOS）
      </div>
      <template v-else>
        <div v-for="ep in endpoints" :key="ep.alias" class="mcp-panel__row">
          <span class="mcp-panel__dot" :class="`mcp-panel__dot--${ep.state}`" />
          <span class="mcp-panel__name">{{ ep.alias }}</span>
          <span class="mcp-panel__tag">{{ ep.transport }}</span>
          <span class="mcp-panel__meta">{{ ep.tool_count }} 工具</span>
          <span v-if="ep.transport === 'stdio'" class="mcp-panel__meta">重启 {{ ep.restart_count }} 次</span>
          <span class="mcp-panel__meta mcp-panel__meta--right">{{ stateLabel(ep.state) }}</span>
        </div>
        <div
          v-for="ep in endpoints.filter((e) => e.last_error)"
          :key="`err-${ep.alias}`"
          class="mcp-panel__row-error"
        >
          {{ ep.alias }}: {{ ep.last_error }}
        </div>
      </template>
    </section>

    <section class="mcp-panel__section">
      <h3 class="mcp-panel__section-title">工具清单（{{ tools.length }}）</h3>
      <div class="mcp-panel__rows">
        <div v-for="tool in tools" :key="tool.name" class="mcp-panel__row">
          <span class="mcp-panel__tool-name">{{ tool.name }}</span>
          <span class="mcp-panel__tag" :class="{ 'mcp-panel__tag--local': tool.source === 'local' }">
            {{ tool.source }}
          </span>
          <span class="mcp-panel__desc">{{ tool.description }}</span>
        </div>
      </div>
    </section>

    <section class="mcp-panel__section">
      <div class="mcp-panel__section-head">
        <h3 class="mcp-panel__section-title">调用流水（{{ callsTotal }}）</h3>
        <select v-model="statusFilter" class="mcp-panel__select" @change="load">
          <option value="">全部状态</option>
          <option value="success">success</option>
          <option value="error">error</option>
          <option value="timeout">timeout</option>
        </select>
      </div>
      <div v-if="calls.length === 0" class="mcp-panel__empty">暂无调用记录</div>
      <div v-else class="mcp-panel__rows">
        <template v-for="call in calls" :key="call.id">
          <button class="mcp-panel__row mcp-panel__row--button" @click="toggleCall(call.id)">
            <span
              class="mcp-panel__dot"
              :class="`mcp-panel__dot--${call.status === 'success' ? 'healthy' : 'error'}`"
            />
            <span class="mcp-panel__tool-name">{{ call.tool_name }}</span>
            <span class="mcp-panel__tag">{{ call.endpoint_alias }}</span>
            <span class="mcp-panel__meta">{{ formatDuration(call.duration_ms) }}</span>
            <span class="mcp-panel__meta">{{ call.status }}</span>
            <span class="mcp-panel__meta mcp-panel__meta--right">{{ formatTime(call.created_at) }}</span>
          </button>
          <div v-if="expandedCallId === call.id" class="mcp-panel__call-detail">
            <pre class="mcp-panel__code">{{ call.arguments_snapshot }}</pre>
            <pre class="mcp-panel__code">{{ call.result_snapshot }}</pre>
            <p v-if="call.error_message" class="mcp-panel__error">{{ call.error_message }}</p>
            <button
              v-if="call.trace_id"
              class="mcp-panel__trace-link"
              @click="emit('openTrace', call.trace_id)"
            >
              查看链路 →
            </button>
          </div>
        </template>
      </div>
    </section>
  </div>
</template>

<style scoped>
.mcp-panel {
  height: 100%;
  overflow-y: auto;
  background: var(--color-bg);
}
.mcp-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--color-border);
}
.mcp-panel__title {
  font-family: var(--font-display);
  font-size: 1rem;
}
.mcp-panel__refresh {
  padding: 0.25rem 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-button);
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 0.75rem;
  cursor: pointer;
  transition: background var(--dur-fast) var(--ease-out-quart);
}
.mcp-panel__refresh:hover {
  background: var(--color-bg-elevated);
}
.mcp-panel__section {
  padding: 0.75rem 1rem 1rem;
}
.mcp-panel__section + .mcp-panel__section {
  border-top: 1px solid var(--color-border);
}
.mcp-panel__section-title {
  margin: 0 0 0.5rem;
  font-family: var(--font-ui);
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--color-text-secondary);
}
.mcp-panel__section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.mcp-panel__select {
  padding: 0.125rem 0.375rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-button);
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
  font-size: 0.75rem;
}
.mcp-panel__rows {
  border-top: 1px solid var(--color-border);
}
.mcp-panel__row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  padding: 0.375rem 0.25rem;
  border: none;
  border-bottom: 1px solid var(--color-border);
  background: transparent;
  font-family: var(--font-ui);
  font-size: 0.75rem;
  color: var(--color-text-primary);
  text-align: left;
}
.mcp-panel__row--button {
  cursor: pointer;
}
.mcp-panel__row--button:hover {
  background: var(--color-bg-elevated);
}
.mcp-panel__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  background: var(--color-danger);
  opacity: 0.5;
}
.mcp-panel__dot--healthy {
  background: var(--color-success);
  opacity: 1;
}
.mcp-panel__dot--error,
.mcp-panel__dot--dead {
  background: var(--color-danger);
  opacity: 1;
}
.mcp-panel__name {
  font-weight: 500;
}
.mcp-panel__tool-name {
  font-family: var(--font-mono);
  font-size: 0.7rem;
}
.mcp-panel__tag {
  padding: 0 0.375rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-seal);
  font-family: var(--font-mono);
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
}
.mcp-panel__tag--local {
  color: var(--color-accent);
  border-color: var(--color-accent);
}
.mcp-panel__meta {
  color: var(--color-text-secondary);
  font-size: 0.6875rem;
}
.mcp-panel__meta--right {
  margin-left: auto;
}
.mcp-panel__desc {
  color: var(--color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mcp-panel__row-error {
  padding: 0.375rem 0.25rem;
  border-bottom: 1px solid var(--color-border);
  font-family: var(--font-mono);
  font-size: 0.6875rem;
  color: var(--color-danger);
}
.mcp-panel__empty {
  padding: 0.75rem 0.25rem;
  color: var(--color-text-secondary);
  font-size: 0.8125rem;
}
.mcp-panel__call-detail {
  padding: 0.5rem 0.5rem 0.75rem 1rem;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg-elevated);
}
.mcp-panel__code {
  margin: 0 0 0.375rem;
  padding: 0.375rem 0.5rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-inner);
  font-family: var(--font-mono);
  font-size: 0.6875rem;
  color: var(--color-text-primary);
  white-space: pre-wrap;
  word-break: break-all;
}
.mcp-panel__error {
  margin: 0 0 0.375rem;
  font-family: var(--font-mono);
  font-size: 0.6875rem;
  color: var(--color-danger);
}
.mcp-panel__trace-link {
  padding: 0;
  border: none;
  background: transparent;
  color: var(--color-accent);
  font-size: 0.75rem;
  cursor: pointer;
}
</style>
