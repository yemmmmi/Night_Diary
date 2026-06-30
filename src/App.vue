<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import CustomTitlebar from '@/shared/components/CustomTitlebar.vue'
import GameButton from '@/shared/components/GameButton.vue'
import NavTabs from '@/shared/components/NavTabs.vue'
import PageTransition from '@/shared/components/PageTransition.vue'
import ParticleBackground from '@/shared/components/ParticleBackground.vue'
import { useSettingsStore } from '@/stores/settings'
import { useBackend } from '@/shared/composables/useBackend'

const route = useRoute()
const settings = useSettingsStore()
settings.load()
const { ready, coreReady, loading, error, startupProgress, init } = useBackend()
const errorDismissed = ref(false)

watch(error, () => {
  errorDismissed.value = false
})

function dismissError() {
  errorDismissed.value = true
}

const isTauri = computed(
  () => typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window,
)

const subtleParticles = computed(() => route.path.startsWith('/write'))

const tabRouteNames = new Set([
  'home',
  'weekly',
  'memory',
  'review',
  'review-detail',
  'chat',
  'models',
])

const isTabRoute = computed(() => {
  const name = route.name as string | null
  return name != null && tabRouteNames.has(name)
})

const tabViewNames = ['HomeScene', 'WeeklyScene', 'MemoryScene', 'ReviewScene', 'ChatScene', 'ModelsScene']

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

</script>

<template>
  <div class="app-root">
    <ParticleBackground :subtle="subtleParticles" />

    <CustomTitlebar v-if="isTauri" />

    <NavTabs v-if="isTabRoute" :frameless="isTauri" />

    <div
      class="app-shell particle-layer"
      :class="{ 'app-shell--frameless': isTauri }"
    >
      <p v-if="statusBanner" class="app-status-banner" role="status">
        {{ statusBanner }}
      </p>

      <template v-if="isTabRoute">
        <router-view v-slot="{ Component, route: r }">
          <keep-alive :include="tabViewNames">
            <component :is="Component" :key="r.name" />
          </keep-alive>
        </router-view>
      </template>
      <template v-else>
        <PageTransition>
          <RouterView />
        </PageTransition>
      </template>
    </div>

    <Teleport to="body">
      <div
        v-if="error && !errorDismissed"
        class="app-error-overlay"
        role="alertdialog"
        aria-labelledby="app-error-title"
      >
        <div class="app-error-card">
          <div class="app-error-card__header">
            <p id="app-error-title" class="app-error-card__title">无法连接本地 AI 引擎</p>
            <button
              type="button"
              class="app-error-card__close"
              aria-label="关闭"
              @click="dismissError"
            >
              &times;
            </button>
          </div>
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

.app-error-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
}

.app-error-card__title {
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.app-error-card__close {
  flex-shrink: 0;
  width: 1.75rem;
  height: 1.75rem;
  border: none;
  border-radius: 0.375rem;
  background: transparent;
  font-size: 1.25rem;
  line-height: 1;
  color: var(--color-text-secondary);
  cursor: pointer;
}

.app-error-card__close:hover {
  background: var(--color-bg-elevated-2);
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
