<script setup lang="ts">
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? '(not set)'
</script>

<template>
  <main
    class="min-h-screen flex flex-col items-center justify-center gap-3 bg-slate-50 text-slate-900"
  >
    <h1 class="text-4xl font-semibold tracking-tight">Night Diary V2</h1>
    <p class="text-slate-500">脚手架已就绪 · Phase 0</p>
    <code class="rounded bg-slate-200 px-3 py-1 text-sm text-slate-700">
      VITE_API_BASE_URL = {{ apiBaseUrl }}
    </code>
  </main>
</template>
