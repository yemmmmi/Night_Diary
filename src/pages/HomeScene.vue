<script setup lang="ts">
import { useBackend } from '@/shared/composables/useBackend'

const { baseUrl } = useBackend()
</script>

<template>
  <main class="home-scene">
    <div class="home-scene__inner stagger-item">
      <h1 class="home-scene__title">夜记</h1>
      <p class="home-scene__subtitle">桌面端已就绪 · Phase D-1 设计系统</p>
      <code class="home-scene__code">API = {{ baseUrl }}</code>
      <div class="home-scene__actions">
        <RouterLink to="/design-system" class="home-link home-link--primary">
          设计系统预览
        </RouterLink>
        <RouterLink to="/settings" class="home-link home-link--secondary">
          LLM 设置
        </RouterLink>
      </div>
    </div>
  </main>
</template>

<style scoped>
.home-scene {
  min-height: calc(100vh - 2.5rem);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2rem 1.5rem;
}

.home-scene__inner {
  text-align: center;
  max-width: 28rem;
}

.home-scene__title {
  font-size: 2.25rem;
  font-weight: 700;
  color: var(--color-text-primary);
}

.home-scene__subtitle {
  margin-top: 0.5rem;
  color: var(--color-text-secondary);
}

.home-scene__code {
  display: inline-block;
  margin-top: 1rem;
  padding: 0.375rem 0.75rem;
  border-radius: 0.5rem;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
}

.home-scene__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  justify-content: center;
  margin-top: 1.5rem;
}

.home-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0.625rem 1.25rem;
  border-radius: var(--radius-button);
  font-size: 0.875rem;
  font-weight: 600;
  text-decoration: none;
  transition:
    transform var(--motion-duration) var(--motion-ease),
    background-color var(--motion-duration) var(--motion-ease);
}

.home-link:hover {
  transform: scale(1.02);
}

.home-link--primary {
  background: var(--color-accent);
  color: var(--color-bg);
}

.home-link--secondary {
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
  border: 1px solid var(--color-border);
}
</style>
