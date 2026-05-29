<script setup lang="ts">
import { useBackend } from '@/shared/composables/useBackend'

const { ready, loading, error, baseUrl } = useBackend()
</script>

<template>
  <div
    v-if="loading"
    class="min-h-screen flex flex-col items-center justify-center gap-3 bg-slate-900 text-slate-100"
  >
    <p class="text-lg">正在连接 AI 引擎…</p>
    <p class="text-sm text-slate-400">等待 Python sidecar 就绪</p>
  </div>

  <div
    v-else-if="error"
    class="min-h-screen flex flex-col items-center justify-center gap-3 bg-slate-900 text-red-300 px-6"
  >
    <p class="text-lg font-medium">无法连接后端</p>
    <p class="text-sm text-slate-400 text-center max-w-md">{{ error }}</p>
  </div>

  <main
    v-else-if="ready"
    class="min-h-screen flex flex-col items-center justify-center gap-3 bg-slate-50 text-slate-900"
  >
    <h1 class="text-4xl font-semibold tracking-tight">Night Diary V2</h1>
    <p class="text-slate-500">桌面端已就绪 · Phase A</p>
    <code class="rounded bg-slate-200 px-3 py-1 text-sm text-slate-700">
      API = {{ baseUrl }}
    </code>
  </main>
</template>
