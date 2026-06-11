<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import CustomTitlebar from '@/shared/components/CustomTitlebar.vue'
import GameButton from '@/shared/components/GameButton.vue'
import PageTransition from '@/shared/components/PageTransition.vue'
import ParticleBackground from '@/shared/components/ParticleBackground.vue'
import { useBackend } from '@/shared/composables/useBackend'

const route = useRoute()
const { ready, coreReady, loading, error, startupProgress, init } = useBackend()

const isTauri = computed(
  () => typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window,
)

const subtleParticles = computed(() => route.path.startsWith('/write'))

const loadingHint = computed(() => {
  if (startupProgress.value != null) {
    return `正在唤醒本地 AI（约需 3–5 秒）…`
  }
  return '首次启动约需 3–5 秒，请稍候'
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
      <p class="text-lg">正在准备夜记…</p>
      <p class="text-sm text-secondary">{{ loadingHint }}</p>
    </div>

    <div
      v-else-if="error"
      class="app-state particle-layer"
      :class="{ 'app-state--frameless': isTauri }"
    >
      <p class="text-lg font-medium">无法启动本地 AI 引擎</p>
      <p class="text-sm text-secondary text-center max-w-md">{{ error }}</p>
      <p class="text-xs text-secondary text-center max-w-md mt-1">
        请检查网络代理设置，确保本地连接未被拦截
      </p>
      <GameButton class="mt-4" variant="secondary" @click="init">重试连接</GameButton>
    </div>

    <div
      v-else-if="ready"
      class="app-shell particle-layer"
      :class="{ 'app-shell--frameless': isTauri }"
    >
      <p v-if="!coreReady" class="app-core-banner" role="status">
        正在加载 AI 引擎组件…
      </p>
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

.app-core-banner {
  position: sticky;
  top: 0;
  z-index: 2;
  margin: 0 0 0.5rem;
  padding: 0.375rem 0.75rem;
  border-radius: 0.5rem;
  font-size: 0.8125rem;
  text-align: center;
  color: var(--color-text-secondary);
  background: color-mix(in srgb, var(--color-accent) 10%, var(--color-surface-raised));
  border: 1px solid color-mix(in srgb, var(--color-accent) 25%, transparent);
}
</style>
