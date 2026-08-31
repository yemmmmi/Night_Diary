<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import GameButton from '@/shared/components/GameButton.vue'
import NavTabs from '@/shared/components/NavTabs.vue'
import PageTransition from '@/shared/components/PageTransition.vue'
import { useSettingsStore } from '@/stores/settings'
import { useBackend } from '@/shared/composables/useBackend'
import { useMiddlewareStatus } from '@/shared/composables/useMiddlewareStatus'

const route = useRoute()
const settings = useSettingsStore()
settings.load()
const { ready, coreReady, loading, error, startupProgress, init } = useBackend()
const { degraded: middlewareDegraded, start: startMiddlewarePolling } =
  useMiddlewareStatus()
const errorDismissed = ref(false)

// 开发者模式开启后开始轮询中间件状态（降级横幅数据源）。
watch(
  () => settings.developerMode,
  (dev) => {
    if (dev) startMiddlewarePolling()
  },
  { immediate: true },
)

watch(error, () => {
  errorDismissed.value = false
})

function dismissError() {
  errorDismissed.value = true
}

const tabRouteNames = new Set(['home', 'plan', 'memory', 'chat'])

const isTabRoute = computed(() => {
  const name = route.name as string | null
  return name != null && tabRouteNames.has(name)
})

const tabViewNames = ['TimelineScene', 'PlanScene', 'MemoryScene', 'ChatScene']

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
    <NavTabs v-if="isTabRoute" />

    <div class="app-shell">
      <p v-if="statusBanner" class="app-status-banner" role="status">
        {{ statusBanner }}
      </p>

      <!-- 降级状态提示（仅开发者模式，robustness P1-5） -->
      <p
        v-if="settings.developerMode && middlewareDegraded"
        class="app-degraded-banner"
        role="status"
      >
        ⚠️ 部分服务降级中：Redis / Neo4j / RQ / LangGraph / 记忆层不可用时自动回退，
        MySQL / LLM 不可用时功能受限
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

.app-degraded-banner {
  position: sticky;
  top: 2.25rem;
  z-index: 2;
  margin: 0 0 0.5rem;
  padding: 0.375rem 0.75rem;
  border-radius: 0.5rem;
  font-size: 0.75rem;
  text-align: center;
  color: var(--color-warning, #b45309);
  background: color-mix(in srgb, var(--color-warning, #f59e0b) 12%, var(--color-surface-raised));
  border: 1px solid color-mix(in srgb, var(--color-warning, #f59e0b) 30%, transparent);
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
