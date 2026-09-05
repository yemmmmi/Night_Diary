<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PhArrowLeft, PhCaretRight } from '@phosphor-icons/vue'

import BackupManager from '@/features/settings/BackupManager.vue'
import DeveloperToggle from '@/features/settings/DeveloperToggle.vue'
import SettingsSection from '@/features/settings/SettingsSection.vue'
import ThemeToggle from '@/features/settings/ThemeToggle.vue'
import { getStats, type AppStats } from '@/shared/api/settings'
import { useSettingsStore } from '@/stores/settings'

const route = useRoute()
const router = useRouter()
const settings = useSettingsStore()
settings.load()

const openSection = ref('general')
const sectionIds = ['general', 'backup', 'about'] as const
const usageStats = ref<AppStats | null>(null)
const statsLoading = ref(true)

function syncSectionFromRoute() {
  const hash = route.hash.replace('#', '')
  if (sectionIds.includes(hash as (typeof sectionIds)[number])) {
    openSection.value = hash
    return
  }
  if (route.path.endsWith('/backup')) openSection.value = 'backup'
}

function toggleSection(id: string) {
  openSection.value = openSection.value === id ? '' : id
  router.replace({ path: '/settings', hash: openSection.value ? `#${openSection.value}` : undefined })
}

async function loadAbout() {
  statsLoading.value = true
  try {
    usageStats.value = await getStats()
  } catch {
    usageStats.value = null
  } finally {
    statsLoading.value = false
  }
}

onMounted(() => {
  syncSectionFromRoute()
  void loadAbout()
})

watch(
  () => [route.hash, route.path],
  () => {
    syncSectionFromRoute()
  },
)
</script>

<template>
  <main class="settings-scene">
    <div class="settings-scene__container">
      <header class="settings-scene__header">
        <RouterLink to="/" class="settings-scene__back">
          <PhArrowLeft :size="16" />
          返回
        </RouterLink>
        <div class="settings-scene__title-area">
          <h1 class="settings-scene__title">设置</h1>
          <p class="settings-scene__subtitle">偏好、AI 模型与本地数据管理</p>
        </div>
      </header>

      <div class="settings-scene__privacy">
        <p class="privacy-block__title">夜记完全运行在你的电脑上</p>
        <p class="privacy-block__text">日记与 AI 调用均不经过第三方服务器，无需注册或登录。</p>
      </div>

      <SettingsSection
        id="general"
        title="通用"
        subtitle="昵称、主题与音效"
        :open="openSection === 'general'"
        @toggle="toggleSection"
      >
        <label class="settings-field">
          <span class="settings-field__label">称呼（可选）</span>
          <input
            v-model="settings.nickname"
            class="settings-field__input ink-underline"
            maxlength="24"
            placeholder="夜记如何称呼你"
          />
        </label>
        <ThemeToggle />
        <label class="settings-field settings-field--checkbox">
          <input v-model="settings.soundEnabled" type="checkbox" />
          <span>启用界面音效</span>
        </label>
        <DeveloperToggle />
      </SettingsSection>

      <RouterLink to="/models" class="settings-scene__llm-link">
        <div class="settings-scene__llm-link-body">
          <span class="settings-scene__llm-link-title">AI 模型</span>
          <span class="settings-scene__llm-link-desc">配置 DeepSeek、通义千问、智谱等模型 API</span>
        </div>
        <PhCaretRight :size="18" class="settings-scene__llm-link-arrow" />
      </RouterLink>

      <SettingsSection
        id="backup"
        title="备份"
        subtitle="手动备份与退出时自动备份"
        :open="openSection === 'backup'"
        @toggle="toggleSection"
      >
        <BackupManager />
      </SettingsSection>

      <SettingsSection
        id="about"
        title="关于"
        subtitle="版本与用量统计"
        :open="openSection === 'about'"
        @toggle="toggleSection"
      >
        <p v-if="statsLoading" class="about-line">加载统计…</p>
        <dl v-else-if="usageStats" class="usage-stats">
          <div class="usage-stats__row"><dt>日记总数</dt><dd>{{ usageStats.diary_count }}</dd></div>
          <div class="usage-stats__row"><dt>LLM 调用次数</dt><dd>{{ usageStats.llm_call_count }}</dd></div>
          <div class="usage-stats__row"><dt>累计 Token</dt><dd>{{ usageStats.total_token_cost }}</dd></div>
        </dl>
      </SettingsSection>
    </div>
  </main>
</template>

<style scoped>
.settings-scene {
  min-height: calc(100vh - 2.5rem);
  padding: 1.25rem 1rem 2rem;
}

.settings-scene__container {
  max-width: 42rem;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.settings-scene__header {
  display: flex;
  align-items: flex-start;
  gap: 0.875rem;
  margin-bottom: 0.25rem;
}

.settings-scene__back {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  margin-top: 0.25rem;
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  text-decoration: none;
  transition: color var(--dur-fast) var(--ease-out-quart);
}

.settings-scene__back:hover {
  color: var(--color-text-primary);
}

.settings-scene__title {
  font-size: 1.35rem;
  font-weight: 700;
  color: var(--color-text-primary);
}

.settings-scene__subtitle {
  margin-top: 0.25rem;
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
}

/* 隐私说明：细线行淡墨，不做卡片。 */
.settings-scene__privacy {
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

.settings-field {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  margin-bottom: 0.875rem;
}

.settings-field--checkbox {
  flex-direction: row;
  align-items: center;
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
}

.settings-field--checkbox input {
  accent-color: var(--color-accent);
}

.settings-field__label {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
}

/* 底线输入：边框与聚焦生长线由全局 ink-underline 提供 */
.settings-field__input {
  padding: 0.375rem 0.125rem;
  border-radius: 0;
  color: var(--color-text-primary);
  font-size: 0.875rem;
}

.settings-field__input::placeholder {
  color: var(--color-text-faint);
}

.about-line {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  margin-bottom: 0.75rem;
}

.usage-stats {
  display: flex;
  flex-direction: column;
}

.usage-stats__row {
  display: flex;
  justify-content: space-between;
  padding: 0.5rem 0.125rem;
  border-bottom: 1px solid var(--color-line);
  font-size: 0.8125rem;
}

.usage-stats__row:last-child {
  border-bottom: none;
}

.usage-stats__row dt {
  color: var(--color-text-secondary);
}

.usage-stats__row dd {
  margin: 0;
  font-weight: 600;
  color: var(--color-text-primary);
  font-variant-numeric: tabular-nums;
}

.settings-field__hint {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  margin-top: 0.375rem;
}

/* 模型入口：细线行 + caret，与分节同一节奏。 */
.settings-scene__llm-link {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.875rem 0.125rem;
  border-top: 1px solid var(--color-line);
  text-decoration: none;
}

.settings-scene__llm-link-title {
  display: block;
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text-primary);
  transition: color var(--dur-fast) var(--ease-out-quart);
}

.settings-scene__llm-link:hover .settings-scene__llm-link-title {
  color: var(--color-accent);
}

.settings-scene__llm-link-desc {
  display: block;
  margin-top: 0.25rem;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

.settings-scene__llm-link-arrow {
  color: var(--color-text-faint);
  flex-shrink: 0;
  transition: transform var(--dur-fast) var(--ease-out-quart);
}

.settings-scene__llm-link:hover .settings-scene__llm-link-arrow {
  transform: translateX(2px);
}
</style>
