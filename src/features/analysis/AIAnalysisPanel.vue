<script setup lang="ts">
import { computed, ref } from 'vue'
import { PhCaretDown, PhCaretUp, PhEnvelopeSimple } from '@phosphor-icons/vue'

import FeedbackButtons from '@/features/analysis/FeedbackButtons.vue'
import AITypingIndicator from '@/shared/components/AITypingIndicator.vue'
import GlassPanel from '@/shared/components/GlassPanel.vue'
import type { AnalysisRecord } from '@/shared/api/analysis'
import type { DiaryEntry } from '@/shared/api/diary'
import { diarySummary } from '@/shared/utils/diaryFormat'

const props = defineProps<{
  entry: DiaryEntry
  analysis: AnalysisRecord | null
  loading?: boolean
  triggering?: boolean
}>()

defineEmits<{
  trigger: []
}>()

const showTokenDetail = ref(false)

const aiText = computed(
  () => props.analysis?.ai_ans?.trim() || props.entry.ai_ans?.trim() || '',
)

const hasAnalysis = computed(() => Boolean(aiText.value) && !props.triggering && !props.loading)

const canFeedback = computed(() => Boolean(props.analysis?.id))

const formattedDate = computed(() => {
  const raw = props.entry.date ?? props.entry.created_at
  const date = props.entry.date
    ? new Date(`${props.entry.date}T00:00:00`)
    : new Date(raw)
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
})

const tierLabel = computed(() => {
  const tier = props.analysis?.execution_tier
  if (!tier) return null
  const map: Record<string, string> = {
    light: '轻量',
    medium: '标准',
    heavy: '深度',
    default: '默认',
  }
  return map[tier] ?? tier
})
</script>

<template>
  <div class="analysis-panel">
    <GlassPanel elevated class="analysis-panel__diary">
      <p class="analysis-panel__diary-date">{{ formattedDate }}</p>
      <p class="analysis-panel__diary-preview font-diary">
        {{ diarySummary(entry.content, 160) }}
      </p>
    </GlassPanel>

    <section v-if="triggering || loading" class="analysis-panel__waiting">
      <AITypingIndicator label="夜记正在读你的日记…" />
    </section>

    <Transition name="letter-in">
      <GlassPanel v-if="hasAnalysis && !triggering" elevated class="analysis-panel__letter">
        <div class="analysis-panel__letter-head">
          <PhEnvelopeSimple :size="20" weight="duotone" class="analysis-panel__letter-icon" />
          <div>
            <p class="analysis-panel__letter-title">夜记的回信</p>
            <p v-if="tierLabel" class="analysis-panel__letter-meta">分析模式 · {{ tierLabel }}</p>
          </div>
        </div>

        <p class="analysis-panel__letter-body font-diary">{{ aiText }}</p>

        <div v-if="canFeedback" class="analysis-panel__feedback">
          <FeedbackButtons :analysis-id="analysis!.id" />
        </div>

        <p v-if="analysis?.agent_mode === 'fallback'" class="analysis-panel__fallback-hint">
          本次未成功调用 AI 模型（可能是未配置或未启用模型）。请前往
          <RouterLink to="/settings">设置</RouterLink>
          添加 DeepSeek API 并勾选「设为该层级的当前使用模型」，然后重新获取回信。
        </p>

        <div v-if="analysis?.token_cost != null" class="analysis-panel__tokens">
          <button type="button" class="analysis-panel__tokens-toggle" @click="showTokenDetail = !showTokenDetail">
            <span>消耗 {{ analysis.token_cost }} tokens</span>
            <PhCaretUp v-if="showTokenDetail" :size="14" />
            <PhCaretDown v-else :size="14" />
          </button>
          <div v-if="showTokenDetail" class="analysis-panel__tokens-detail">
            <div class="analysis-panel__tokens-row">
              <span>缓存命中</span>
              <span>{{ analysis.cache_hit_tokens ?? 0 }}</span>
            </div>
            <div class="analysis-panel__tokens-row">
              <span>输入</span>
              <span>{{ analysis.cache_miss_tokens ?? 0 }}</span>
            </div>
            <div class="analysis-panel__tokens-row">
              <span>输出</span>
              <span>{{ analysis.output_tokens ?? 0 }}</span>
            </div>
          </div>
        </div>
      </GlassPanel>
    </Transition>

    <slot name="actions" />
  </div>
</template>

<style scoped>
.analysis-panel {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.analysis-panel__diary-date {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  margin-bottom: 0.5rem;
}

.analysis-panel__diary-preview {
  font-size: 0.9375rem;
  line-height: 1.65;
  color: var(--color-text-secondary);
  white-space: pre-wrap;
}

.analysis-panel__waiting {
  display: flex;
  justify-content: center;
  padding: 2rem 0;
}

.analysis-panel__letter {
  border-left: 3px solid var(--color-accent);
}

.analysis-panel__letter-head {
  display: flex;
  align-items: flex-start;
  gap: 0.625rem;
  margin-bottom: 1rem;
}

.analysis-panel__letter-icon {
  color: var(--color-accent);
  flex-shrink: 0;
  margin-top: 0.125rem;
}

.analysis-panel__letter-title {
  font-size: 1rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.analysis-panel__letter-meta {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  margin-top: 0.125rem;
}

.analysis-panel__letter-body {
  font-size: 1.0625rem;
  line-height: 1.75;
  color: var(--color-text-primary);
  white-space: pre-wrap;
}

.analysis-panel__fallback-hint {
  margin-top: 0.75rem;
  padding: 0.625rem 0.75rem;
  border-radius: 0.5rem;
  font-size: 0.8125rem;
  color: var(--color-warning);
  background: color-mix(in srgb, var(--color-warning) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-warning) 30%, transparent);
}

.analysis-panel__fallback-hint a {
  color: var(--color-accent);
}

.analysis-panel__feedback {
  margin-top: 1.25rem;
  padding-top: 1rem;
  border-top: 1px solid var(--color-border);
}

.analysis-panel__tokens {
  margin-top: 1rem;
}

.analysis-panel__tokens-toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
}

.analysis-panel__tokens-detail {
  margin-top: 0.625rem;
  padding: 0.75rem;
  border-radius: 0.625rem;
  background: var(--color-surface-sunken);
  font-size: 0.75rem;
}

.analysis-panel__tokens-row {
  display: flex;
  justify-content: space-between;
  color: var(--color-text-secondary);
  padding: 0.125rem 0;
}

.letter-in-enter-active {
  transition:
    opacity 0.5s ease,
    transform 0.5s ease;
}

.letter-in-enter-from {
  opacity: 0;
  transform: translateY(12px);
}
</style>
