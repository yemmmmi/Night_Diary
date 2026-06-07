<script setup lang="ts">
import { useBackend } from '@/shared/composables/useBackend'

const { ready, loading, error } = useBackend()
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

  <RouterView v-else-if="ready" />
</template>
