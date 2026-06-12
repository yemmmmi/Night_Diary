<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { getCurrentWindow } from '@tauri-apps/api/window'

import CustomTitlebar from '@/shared/components/CustomTitlebar.vue'
import GameButton from '@/shared/components/GameButton.vue'
import PageTransition from '@/shared/components/PageTransition.vue'
import ParticleBackground from '@/shared/components/ParticleBackground.vue'
import { createBackup } from '@/shared/api/settings'
import { useBackend } from '@/shared/composables/useBackend'
import { useSettingsStore } from '@/stores/settings'

const route = useRoute()
const settings = useSettingsStore()
settings.load()
const { ready, coreReady, loading, error, startupProgress, init } = useBackend()



const isTauri = computed(

  () => typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window,

)



const subtleParticles = computed(() => route.path.startsWith('/write'))



const statusBanner = computed(() => {

  if (error.value) return null

  if (loading.value || !ready.value) {

    return startupProgress.value != null

      ? '正在唤醒本地 AI 引擎…'

      : '正在连接本地 AI 引擎…'

  }

  if (!coreReady.value) {

    return '正在加载 AI 引擎组件，日记读写已可用…'

  }

  return null

})

onMounted(async () => {
  if (!isTauri.value) return
  try {
    const win = getCurrentWindow()
    await win.onCloseRequested(async () => {
      if (!settings.autoBackup) return
      try {
        await createBackup()
      } catch {
        // ignore backup errors during shutdown
      }
    })
  } catch {
    // window API unavailable in tests
  }
})

</script>



<template>

  <div class="app-root">

    <ParticleBackground :subtle="subtleParticles" />



    <CustomTitlebar v-if="isTauri" />



    <div

      class="app-shell particle-layer"

      :class="{ 'app-shell--frameless': isTauri }"

    >

      <p v-if="statusBanner" class="app-status-banner" role="status">

        {{ statusBanner }}

      </p>



      <PageTransition>

        <RouterView />

      </PageTransition>

    </div>



    <Teleport to="body">

      <div

        v-if="error"

        class="app-error-overlay"

        role="alertdialog"

        aria-labelledby="app-error-title"

      >

        <div class="app-error-card">

          <p id="app-error-title" class="app-error-card__title">无法连接本地 AI 引擎</p>

          <p class="app-error-card__detail">{{ error }}</p>

          <p class="app-error-card__hint">

            界面仍可浏览；修复连接后可正常使用日记与 AI 功能

          </p>

          <GameButton variant="secondary" @click="init">重试连接</GameButton>

        </div>

      </div>

    </Teleport>

  </div>

</template>



<style scoped>

.app-root {

  position: relative;

  min-height: 100vh;

}



.app-shell {

  min-height: 100vh;

}



.app-shell--frameless {

  padding-top: 2.5rem;

}



.app-status-banner {

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



.app-error-overlay {

  position: fixed;

  inset: 0;

  z-index: 200;

  display: flex;

  align-items: flex-end;

  justify-content: center;

  padding: 1rem;

  pointer-events: none;

}



.app-error-card {

  pointer-events: auto;

  width: min(28rem, 100%);

  padding: 1rem 1.25rem;

  border-radius: var(--radius-outer);

  border: 1px solid color-mix(in srgb, var(--color-danger) 35%, var(--color-border));

  background: var(--color-bg-elevated);

  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);

  display: flex;

  flex-direction: column;

  gap: 0.5rem;

}



.app-error-card__title {

  font-size: 0.9375rem;

  font-weight: 600;

  color: var(--color-text-primary);

}



.app-error-card__detail {

  font-size: 0.8125rem;

  color: var(--color-danger);

}



.app-error-card__hint {

  font-size: 0.75rem;

  color: var(--color-text-secondary);

  margin-bottom: 0.25rem;

}

</style>

