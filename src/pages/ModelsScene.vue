<script setup lang="ts">
import { PhArrowLeft } from '@phosphor-icons/vue'

import LLMConfig from '@/features/settings/LLMConfig.vue'
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

      <div class="models-scene__privacy">
        <p class="privacy-block__title">密钥仅保存在本机</p>
        <p class="privacy-block__text">
          API Key 经 Fernet 加密后存入本地数据库，调用时直连对应厂商，不经过夜记的任何中转服务器。
        </p>
      </div>

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
  margin-top: 0.25rem;
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  text-decoration: none;
  transition: color var(--dur-fast) var(--ease-out-quart);
}

.models-scene__back:hover {
  color: var(--color-text-primary);
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

/* 隐私说明：细线行淡墨，不做卡片。 */
.models-scene__privacy {
  padding: 0.125rem 0.125rem 0.25rem;
}

.privacy-block__title {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--color-text-secondary);
  margin-bottom: 0.25rem;
}

.privacy-block__text {
  font-size: 0.8125rem;
  line-height: 1.7;
  color: var(--color-text-faint);
}
</style>
