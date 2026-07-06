<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PhArrowLeft, PhCaretRight } from '@phosphor-icons/vue'

import BackupManager from '@/features/settings/BackupManager.vue'
import DeveloperToggle from '@/features/settings/DeveloperToggle.vue'
import SettingsSection from '@/features/settings/SettingsSection.vue'
import ThemeToggle from '@/features/settings/ThemeToggle.vue'
import ReplierManager from '@/features/settings/ReplierManager.vue'
import GlassPanel from '@/shared/components/GlassPanel.vue'
import { getAppVersion, getStats, type AppStats } from '@/shared/api/settings'
import { useSettingsStore } from '@/stores/settings'

const route = useRoute()
const router = useRouter()
const settings = useSettingsStore()
settings.load()

const openSection = ref('general')
const sectionIds = ['general', 'replier', 'backup', 'about'] as const
const usageStats = ref<AppStats | null>(null)
const statsLoading = ref(true)
const appVersion = ref<string | null>(null)

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
  appVersion.value = await getAppVersion()
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

      <GlassPanel class="settings-scene__privacy" elevated>
        <p class="privacy-block__title">夜记完全运行在你的电脑上</p>
        <p class="privacy-block__text">日记与 AI 调用均不经过第三方服务器，无需注册或登录。</p>
      </GlassPanel>

      <SettingsSection
        id="general"
        title="通用"
        subtitle="昵称、主题与音效"
        :open="openSection === 'general'"
        @toggle="toggleSection"
      >
        <label class="settings-field">
          <span class="settings-field__label">称呼（可选）</span>
          <input v-model="settings.nickname" class="settings-field__input" maxlength="24" placeholder="夜记如何称呼你" />
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
        id="replier"
        title="回信者"
        subtitle="选择谁给你回信，或创建自己的人设"
        :open="openSection === 'replier'"
        @toggle="toggleSection"
      >
        <ReplierManager />
        <p class="settings-field__hint">切换回信者只影响之后生成的回信，不影响已收到的</p>
      </SettingsSection>

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
        <p v-if="appVersion" class="about-line">版本 {{ appVersion }}</p>
        <p v-if="statsLoading" class="about-line">加载统计…</p>
        <dl v-else-if="usageStats" class="usage-stats">
          <div class="usage-stats__row"><dt>日记总数</dt><dd>{{ usageStats.diary_count }}</dd></div>
          <div class="usage-stats__row"><dt>回信数</dt><dd>{{ usageStats.analysis_count }}</dd></div>
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
  gap: 0.75rem;
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
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  text-decoration: none;
  padding: 0.5rem 0.625rem;
  border-radius: var(--radius-button);
  border: 1px solid var(--color-border);
  background: var(--color-bg-elevated);
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

.settings-field__label {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
}

.settings-field__input {
  padding: 0.625rem 0.75rem;
  border-radius: 0.625rem;
  border: 1px solid var(--color-border);
  background: var(--color-bg-elevated-2);
  color: var(--color-text-primary);
}

.about-line {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  margin-bottom: 0.75rem;
}

.usage-stats {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.usage-stats__row {
  display: flex;
  justify-content: space-between;
  font-size: 0.8125rem;
}

.usage-stats__row dt {
  color: var(--color-text-secondary);
}

.usage-stats__row dd {
  margin: 0;
  font-weight: 600;
  color: var(--color-text-primary);
}

.settings-field__hint {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  margin-top: 0.375rem;
}

.settings-scene__llm-link {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.125rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-outer);
  background: var(--color-bg-elevated);
  text-decoration: none;
  transition: border-color var(--motion-duration) var(--motion-ease);
}

.settings-scene__llm-link:hover {
  border-color: var(--color-accent);
}

.settings-scene__llm-link-title {
  display: block;
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.settings-scene__llm-link-desc {
  display: block;
  margin-top: 0.25rem;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

.settings-scene__llm-link-arrow {
  color: var(--color-text-secondary);
  flex-shrink: 0;
}
</style>
