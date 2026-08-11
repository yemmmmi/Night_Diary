<script setup lang="ts">
import { computed, ref } from 'vue'
import { PhCaretDown, PhCaretUp, PhEnvelopeSimple, PhBrain } from '@phosphor-icons/vue'

import FeedbackButtons from '@/features/analysis/FeedbackButtons.vue'
import AITypingIndicator from '@/shared/components/AITypingIndicator.vue'
import GlassPanel from '@/shared/components/GlassPanel.vue'
import { useSettingsStore } from '@/stores/settings'
import { useAnalysisStore } from '@/stores/analysis'
import type { AnalysisRecord } from '@/shared/api/analysis'
import type { DiaryEntry } from '@/shared/api/diary'
import { diarySummary } from '@/shared/utils/diaryFormat'

const props = defineProps<{
  entry: DiaryEntry
  analysis: AnalysisRecord | null
  loading?: boolean
  triggering?: boolean
  hideDiaryPreview?: boolean
}>()

const settings = useSettingsStore()

// 从 store 取流式 composable（store 持有单例，组件直接消费 replyText/status）。
const analysisStore = useAnalysisStore()
const streamingReply = analysisStore.streamingReply

defineEmits<{
  trigger: []
}>()

const showTokenDetail = ref(false)

// === 流式渲染 ===
// 流式期间（status === 'streaming'）以及 REPLY_END 后到完整记录刷新前
// （triggering 仍为 true），用 streamingReply.replyText 展示打字机文本。
// 注意：通过 store 代理访问时，Pinia 已自动解包 Ref，所以不需要 .value。
const streamingText = computed(() => streamingReply.replyText)
const isStreaming = computed(
  () => streamingReply.status === 'streaming',
)
const showStreamingLetter = computed(
  () => Boolean(streamingText.value) && Boolean(props.triggering),
)

const aiText = computed(
  () => props.analysis?.reply?.trim() || props.entry.reply?.trim() || '',
)

const hasAnalysis = computed(
  () =>
    Boolean(aiText.value) &&
    !props.triggering &&
    !props.loading &&
    !showStreamingLetter.value,
)

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

const modelLabel = computed(() => props.analysis?.model_name?.trim() || null)

const isFallback = computed(() => props.analysis?.agent_mode === 'fallback')

const statusDetail = computed(() => props.analysis?.status_detail?.trim() || null)

const referencedMemoryCount = computed(() => props.analysis?.referenced_memory_count ?? 0)
</script>

<template>
  <div class="analysis-panel">
    <GlassPanel v-if="!hideDiaryPreview" elevated class="analysis-panel__diary">
      <p class="analysis-panel__diary-date">{{ formattedDate }}</p>
      <p class="analysis-panel__diary-preview font-diary">
        {{ diarySummary(entry.content, 160) }}
      </p>
    </GlassPanel>

    <section v-if="(triggering || loading) && !showStreamingLetter" class="analysis-panel__waiting">
      <AITypingIndicator label="正在读你写下的字…" />
    </section>

    <!-- 流式中的打字机渲染：SSE 推送的文本逐字累积 -->
    <Transition name="letter-in">
      <GlassPanel
        v-if="showStreamingLetter"
        elevated
        class="analysis-panel__letter analysis-panel__letter--streaming"
      >
        <div class="analysis-panel__letter-head">
          <PhEnvelopeSimple :size="20" weight="duotone" class="analysis-panel__letter-icon" />
          <div>
            <p class="analysis-panel__letter-title">{{ settings.replierName ? `${settings.replierName}的回信` : '回信' }}</p>
            <p v-if="isStreaming" class="analysis-panel__letter-meta">正在写回信…</p>
          </div>
        </div>

        <p class="analysis-panel__letter-body font-diary">
          {{ streamingText }}<span v-if="isStreaming" class="analysis-panel__cursor">|</span>
        </p>
      </GlassPanel>
    </Transition>

    <Transition name="letter-in">
      <GlassPanel v-if="hasAnalysis && !triggering && !showStreamingLetter" elevated class="analysis-panel__letter">
        <div class="analysis-panel__letter-head">
          <PhEnvelopeSimple :size="20" weight="duotone" class="analysis-panel__letter-icon" />
          <div>
            <p class="analysis-panel__letter-title">{{ settings.replierName ? `${settings.replierName}的回信` : '回信' }}</p>
            <p v-if="tierLabel || modelLabel" class="analysis-panel__letter-meta">
              <template v-if="tierLabel">分析模式 · {{ tierLabel }}</template>
              <template v-if="tierLabel && modelLabel"> · </template>
              <template v-if="modelLabel">模型 · {{ modelLabel }}</template>
            </p>
            <p v-if="referencedMemoryCount > 0" class="analysis-panel__memory-ref">
              <PhBrain :size="12" weight="duotone" />
              本次参考了 {{ referencedMemoryCount }} 条记忆
            </p>
          </div>
        </div>

        <p class="analysis-panel__letter-body font-diary">{{ aiText }}</p>

        <div v-if="canFeedback" class="analysis-panel__feedback">
          <FeedbackButtons :analysis-id="analysis!.id" />
        </div>

        <p v-if="isFallback" class="analysis-panel__fallback-hint">
          <strong>未成功调用 AI 模型。</strong>
          <span v-if="statusDetail">{{ statusDetail }}</span>
          <span v-else>可能是未配置或未启用模型。</span>
          请前往
          <RouterLink to="/settings">设置</RouterLink>
          添加 DeepSeek API 并勾选「设为该层级的当前使用模型」，然后重新获取回信。
        </p>

        <p v-else-if="!modelLabel && hasAnalysis" class="analysis-panel__fallback-hint">
          当前层级未配置活跃模型，可能使用了环境变量或降级模式。请前往
          <RouterLink to="/settings">设置</RouterLink>
          确认模型配置。
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

.analysis-panel__letter--streaming {
  border-left-color: color-mix(in srgb, var(--color-accent) 60%, transparent);
}

.analysis-panel__cursor {
  display: inline-block;
  margin-left: 0.125rem;
  color: var(--color-accent);
  font-weight: 100;
  animation: analysis-panel-cursor-blink 1s step-end infinite;
}

@keyframes analysis-panel-cursor-blink {
  0%,
  50% {
    opacity: 1;
  }
  50.01%,
  100% {
    opacity: 0;
  }
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

.analysis-panel__memory-ref {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  margin-top: 0.25rem;
  font-size: 0.6875rem;
  color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 10%, transparent);
  padding: 0.125rem 0.5rem;
  border-radius: 1rem;
  width: fit-content;
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
