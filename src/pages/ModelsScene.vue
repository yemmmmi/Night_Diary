<script setup lang="ts">
import { PhArrowLeft } from '@phosphor-icons/vue'

import LLMConfig from '@/features/settings/LLMConfig.vue'
import GlassPanel from '@/shared/components/GlassPanel.vue'
import { modelsCopy } from '@/shared/copy/models'

defineOptions({ name: 'ModelsScene' })
</script>

<template>
  <main class="models-scene">
    <div class="models-scene__container">
      <header class="models-scene__header">
        <RouterLink to="/" class="models-scene__back">
          <PhArrowLeft :size="16" />
          返回
        </RouterLink>
        <div class="models-scene__title-area">
          <h1 class="models-scene__title">{{ modelsCopy.pageTitle }}</h1>
          <p class="models-scene__subtitle">{{ modelsCopy.pageSubtitle }}</p>
        </div>
      </header>

      <GlassPanel class="models-scene__privacy" elevated>
        <p class="privacy-block__title">密钥仅保存在本机</p>
        <p class="privacy-block__text">
          API Key 经 Fernet 加密后存入本地数据库，调用时直连对应厂商，不经过夜记的任何中转服务器。
        </p>
      </GlassPanel>

      <LLMConfig />
    </div>
  </main>
</template>

<style scoped>
.models-scene {
  min-height: calc(100vh - 2.5rem);
  padding: 1.25rem 1rem 2rem;
}

.models-scene__container {
  max-width: 44rem;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.models-scene__header {
  display: flex;
  align-items: flex-start;
  gap: 0.875rem;
  margin-bottom: 0.25rem;
}

.models-scene__back {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  text-decoration: none;
  padding: 0.5rem 0.625rem;
  border-radius: var(--radius-button);
  border: 1px solid var(--color-border);
  background: var(--color-bg-elevated);
}

.models-scene__title {
  font-size: 1.35rem;
  font-weight: 700;
  color: var(--color-text-primary);
}

.models-scene__subtitle {
  margin-top: 0.25rem;
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
}

.privacy-block__title {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 0.375rem;
}

.privacy-block__text {
  font-size: 0.8125rem;
  line-height: 1.6;
  color: var(--color-text-secondary);
}
</style>
