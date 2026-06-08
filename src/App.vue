<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import CustomTitlebar from '@/shared/components/CustomTitlebar.vue'
import GameButton from '@/shared/components/GameButton.vue'
import PageTransition from '@/shared/components/PageTransition.vue'
import ParticleBackground from '@/shared/components/ParticleBackground.vue'
import { useBackend } from '@/shared/composables/useBackend'

const route = useRoute()
const { ready, loading, error, startupProgress, init } = useBackend()

const isTauri = computed(
  () => typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window,
)

const subtleParticles = computed(() => route.path.startsWith('/write'))

const loadingHint = computed(() => {
  if (startupProgress.value != null) {
    return `正在启动 Python 引擎（第 ${startupProgress.value} 次探测）…`
  }
  return '等待 Python sidecar 就绪（首次启动约 3–5 秒）'
})
</script>

<template>
  <div class="app-root">
    <ParticleBackground :subtle="subtleParticles" />

    <CustomTitlebar v-if="isTauri" />

    <div
      v-if="loading"
      class="app-state particle-layer"
      :class="{ 'app-state--frameless': isTauri }"
    >
      <p class="text-lg">正在连接 AI 引擎…</p>
      <p class="text-sm text-secondary">{{ loadingHint }}</p>
    </div>

    <div
      v-else-if="error"
      class="app-state particle-layer"
      :class="{ 'app-state--frameless': isTauri }"
    >
      <p class="text-lg font-medium">无法连接后端</p>
      <p class="text-sm text-secondary text-center max-w-md">{{ error }}</p>
      <p class="text-xs text-secondary text-center max-w-md mt-1">
        若开着代理，请确认绕过列表含 127.0.0.0/8
      </p>
      <GameButton class="mt-4" variant="secondary" @click="init">重试连接</GameButton>
    </div>

    <div
      v-else-if="ready"
      class="app-shell particle-layer"
      :class="{ 'app-shell--frameless': isTauri }"
    >
      <PageTransition>
        <RouterView />
      </PageTransition>
    </div>
  </div>
</template>

<style scoped>
.app-root {
  position: relative;
  min-height: 100vh;
}

.app-state,
.app-shell {
  min-height: 100vh;
}

.app-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  padding: 2rem 1.5rem;
}

.app-state--frameless,
.app-shell--frameless {
  padding-top: 2.5rem;
}

.text-secondary {
  color: var(--color-text-secondary);
}
</style>
