<script setup lang="ts">
import { useBackend } from '@/shared/composables/useBackend'

const { baseUrl } = useBackend()
</script>

<template>
  <main class="min-h-screen flex flex-col items-center justify-center gap-3 bg-slate-50 text-slate-900">
    <h1 class="text-4xl font-semibold tracking-tight">Night Diary V2</h1>
    <p class="text-slate-500">桌面端已就绪 · Phase C</p>
    <code class="rounded bg-slate-200 px-3 py-1 text-sm text-slate-700">
      API = {{ baseUrl }}
    </code>
    <RouterLink
      to="/settings"
      class="mt-4 rounded-lg bg-slate-900 px-4 py-2 text-sm text-white hover:bg-slate-800"
    >
      LLM 设置
    </RouterLink>
  </main>
</template>
