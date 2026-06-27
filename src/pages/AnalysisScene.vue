<script setup lang="ts">
import { onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'

/** Legacy route: redirect to diary page with reply anchor. */
const route = useRoute()
const router = useRouter()

onMounted(() => {
  const raw = route.params.diaryId
  const parsed = Number(raw)
  if (Number.isFinite(parsed)) {
    router.replace({ path: `/write/${parsed}`, hash: '#reply' })
    return
  }
  router.replace('/')
})
</script>

<template>
  <main class="analysis-redirect" aria-live="polite">
    <p>正在打开日记…</p>
  </main>
</template>

<style scoped>
.analysis-redirect {
  min-height: 40vh;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-secondary);
  font-size: 0.875rem;
}
</style>
