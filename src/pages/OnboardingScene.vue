<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import GameButton from '@/shared/components/GameButton.vue'
import GlassPanel from '@/shared/components/GlassPanel.vue'
import AITypingIndicator from '@/shared/components/AITypingIndicator.vue'
import BrandMark from '@/shared/components/BrandMark.vue'
import { useBackend } from '@/shared/composables/useBackend'
import { useSound } from '@/shared/composables/useSound'
import { useSettingsStore } from '@/stores/settings'

const router = useRouter()
const settings = useSettingsStore()
settings.load()
const { ready, coreReady, loading, startupProgress } = useBackend()
const { playSuccess } = useSound()

const step = ref(0)
const selectedReplier = ref('preset-warm')

const replierOptions = [
  { key: 'preset-warm', name: '温暖', desc: '以温暖共情的方式回信，像一位耐心的倾听者' },
  { key: 'preset-pragmatic', name: '务实', desc: '简洁直接，就事论事，像老朋友一样坦诚' },
  { key: 'preset-calm', name: '平静', desc: '温和从容，用"没关系，慢慢来"的节奏回应' },
]

const steps = [
  {
    title: '欢迎来到夜记',
    body: '这是一本只属于你的本地日记。写下心情，夜记会在你需要时认真回信。',
  },
  {
    title: 'AI 引擎正在就位',
    body: '首次启动需要加载本地 AI 组件，请稍候片刻。',
  },
  {
    title: '怎么称呼你？',
    body: '可以留空，之后随时在设置里修改。',
  },
  {
    title: '想让谁给你回信？',
    body: '选一位回信者。之后可以在设置中切换，不影响已收到的回信。',
  },
  {
    title: '你可以这样使用',
    body: '首页按周整理日记；写完可获取回信；回顾页浏览历史。',
  },
] as const

const isEngineStep = computed(() => step.value === 1)
const isNicknameStep = computed(() => step.value === 2)
const isReplierStep = computed(() => step.value === 3)
const isLastStep = computed(() => step.value === steps.length - 1)
const engineReady = computed(() => ready.value && coreReady.value)

const progressLabel = computed(() => {
  if (startupProgress.value != null) {
    return `正在加载 AI 组件… ${startupProgress.value}%`
  }
  if (!ready.value || loading.value) return '正在连接本地 AI 引擎…'
  if (!coreReady.value) return '正在加载 AI 组件…'
  return 'AI 引擎已就绪'
})

function nextStep() {
  if (isEngineStep.value && !engineReady.value) return
  if (step.value < steps.length - 1) {
    step.value += 1
    return
  }
  finish()
}

function finish() {
  settings.setActiveReplier(selectedReplier.value)
  settings.completeOnboarding()
  playSuccess()
  void router.replace('/')
}
</script>

<template>
  <main class="onboarding-scene">
    <GlassPanel elevated class="onboarding-scene__card">
      <BrandMark class="onboarding-scene__mark" />
      <h1 class="onboarding-scene__title">{{ steps[step].title }}</h1>
      <p class="onboarding-scene__body">{{ steps[step].body }}</p>

      <div v-if="isEngineStep" class="onboarding-scene__engine">
        <AITypingIndicator v-if="!engineReady" :label="progressLabel" />
        <p v-else class="onboarding-scene__ready">本地 AI 引擎已准备就绪</p>
      </div>

      <label v-if="isNicknameStep" class="onboarding-scene__field">
        <span>称呼</span>
        <input v-model="settings.nickname" maxlength="24" placeholder="例如：小夜" />
      </label>

      <div v-if="isReplierStep" class="onboarding-scene__replier">
        <button
          v-for="opt in replierOptions"
          :key="opt.key"
          type="button"
          class="onboarding-replier-card"
          :class="{ 'is-active': selectedReplier === opt.key }"
          @click="selectedReplier = opt.key"
        >
          <span class="onboarding-replier-name">{{ opt.name }}</span>
          <span class="onboarding-replier-desc">{{ opt.desc }}</span>
        </button>
      </div>

      <div class="onboarding-scene__actions">
        <GameButton
          variant="primary"
          :disabled="isEngineStep && !engineReady"
          @click="nextStep"
        >
          {{ isLastStep ? '开始写日记' : '继续' }}
        </GameButton>
      </div>
    </GlassPanel>
  </main>
</template>

<style scoped>
.onboarding-scene {
  min-height: calc(100vh - 2.5rem);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1.5rem 1rem;
}

.onboarding-scene__card {
  width: min(28rem, 100%);
  padding: 2rem 1.5rem;
  text-align: center;
}

.onboarding-scene__mark {
  width: 3rem;
  height: 3rem;
  margin: 0 auto 1rem;
}

.onboarding-scene__title {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--color-text-primary);
  margin-bottom: 0.625rem;
}

.onboarding-scene__body {
  font-size: 0.9375rem;
  line-height: 1.7;
  color: var(--color-text-secondary);
  margin-bottom: 1.25rem;
}

.onboarding-scene__engine {
  margin-bottom: 1.25rem;
}

.onboarding-scene__ready {
  font-size: 0.875rem;
  color: var(--color-success);
}

.onboarding-scene__field {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  text-align: left;
  margin-bottom: 1.25rem;
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
}

.onboarding-scene__field input {
  padding: 0.625rem 0.75rem;
  border-radius: 0.625rem;
  border: 1px solid var(--color-border);
  background: var(--color-bg-elevated-2);
  color: var(--color-text-primary);
}

.onboarding-scene__actions {
  display: flex;
  justify-content: center;
}

.onboarding-scene__replier {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-bottom: 1.25rem;
}

.onboarding-replier-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
  width: 100%;
  padding: 0.75rem 1rem;
  border: 1px solid var(--color-border);
  border-radius: 0.75rem;
  background: var(--color-bg-elevated);
  cursor: pointer;
  transition: border-color var(--motion-duration) var(--motion-ease);
  text-align: center;
}

.onboarding-replier-card:hover {
  border-color: var(--color-accent-muted);
}

.onboarding-replier-card.is-active {
  border-color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 8%, var(--color-bg-elevated));
}

.onboarding-replier-name {
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.onboarding-replier-desc {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}
</style>
