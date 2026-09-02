<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { PhArrowSquareOut, PhNotePencil, PhSparkle } from '@phosphor-icons/vue'

import type { SkillResult } from '@/shared/api/conversation'
import { chatCopy } from '@/shared/copy/chat'
import { parseLocalDate } from '@/shared/utils/diaryFormat'

const props = defineProps<{
  result: SkillResult
}>()

const router = useRouter()

const recordDateLabel = computed(() => {
  if (props.result.skill !== 'record') return ''
  const date = parseLocalDate(props.result.date)
  if (Number.isNaN(date.getTime())) return props.result.date
  return `${date.getMonth() + 1}月${date.getDate()}日`
})

/* 日记正文默认收成 4 行，长文可展开（浏览场景优先直给，不喧哗） */
const recordOpen = ref(false)

const planSummary = computed(() => {
  if (props.result.skill !== 'plan') return ''
  const { template, target_value: target, tasks } = props.result
  if (template === 'checkin_total') {
    return chatCopy.skillPlanCheckin(Number(target ?? 0))
  }
  if (template === 'timer_daily') {
    const hours = Number(target ?? 0)
    return chatCopy.skillPlanTimer(hours === Math.floor(hours) ? Math.floor(hours) : hours)
  }
  const verified = tasks.filter((t) => t.verified).length
  return chatCopy.skillPlanNodes(tasks.length, verified)
})

function goToPlan() {
  router.push('/plan')
}
</script>

<template>
  <!-- 记录：已录入的日记正文（可展开） -->
  <div v-if="result.skill === 'record'" class="skill-block" data-testid="skill-block-record">
    <p class="skill-block__label">
      <PhNotePencil :size="13" aria-hidden="true" />
      {{ chatCopy.skillRecordLabel }} · {{ recordDateLabel }}
    </p>
    <p
      class="skill-block__body"
      :class="{ 'is-clamped': !recordOpen }"
      data-testid="skill-record-content"
    >
      {{ result.content }}
    </p>
    <button
      v-if="result.content.length > 80"
      type="button"
      class="skill-block__toggle"
      data-testid="skill-record-toggle"
      @click="recordOpen = !recordOpen"
    >
      {{ recordOpen ? chatCopy.skillRecordCollapse : chatCopy.skillRecordExpand }}
    </button>
  </div>

  <!-- 洞悉：匹配到的心理学理论视角（分析本体就是信正文） -->
  <div
    v-else-if="result.skill === 'insight' && result.matched_theories.length > 0"
    class="skill-block"
    data-testid="skill-block-insight"
  >
    <p class="skill-block__label">
      <PhSparkle :size="13" aria-hidden="true" />
      {{ chatCopy.skillInsightLabel }}
    </p>
    <ul class="skill-block__chips">
      <li
        v-for="(theory, index) in result.matched_theories"
        :key="index"
        class="skill-block__chip"
        data-testid="skill-insight-chip"
      >
        {{ theory }}
      </li>
    </ul>
  </div>

  <!-- 计划：新建计划的结构化概要 + 去计划页推进 -->
  <div v-else-if="result.skill === 'plan'" class="skill-block" data-testid="skill-block-plan">
    <p class="skill-block__label">
      <PhArrowSquareOut :size="13" aria-hidden="true" />
      {{ chatCopy.skillPlanLabel }}
    </p>
    <p class="skill-block__plan-title">{{ result.title }}</p>
    <p class="skill-block__plan-meta">{{ planSummary }}</p>
    <button
      type="button"
      class="skill-block__link"
      data-testid="skill-plan-open"
      @click="goToPlan"
    >
      {{ chatCopy.skillPlanOpen }}
    </button>
  </div>
</template>

<style scoped>
/* 技能结果块：细线框 8px 圆角，墨色小字，区别于页边注脚（无左侧竖线） */
.skill-block {
  margin-top: 0.625rem;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--color-line);
  border-radius: 8px;
  font-size: 0.8125rem;
  color: var(--color-text-primary);
}

.skill-block__label {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  margin: 0;
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
  letter-spacing: 0.05em;
}

.skill-block__body {
  margin: 0.375rem 0 0;
  font-family: var(--font-diary);
  font-size: 0.8125rem;
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-word;
}

.skill-block__body.is-clamped {
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.skill-block__toggle,
.skill-block__link {
  border: none;
  background: none;
  padding: 0;
  margin-top: 0.375rem;
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
  text-decoration: underline;
  text-underline-offset: 3px;
  cursor: pointer;
}

.skill-block__toggle:hover,
.skill-block__link:hover {
  color: var(--color-accent);
}

/* 洞悉理论：灰墨底小签 */
.skill-block__chips {
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  margin: 0.5rem 0 0;
  padding: 0;
}

.skill-block__chip {
  padding: 0.125rem 0.5rem;
  border: 1px solid var(--color-line);
  border-radius: 999px;
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
  background: color-mix(in srgb, var(--color-ink) 4%, transparent);
}

.skill-block__plan-title {
  margin: 0.375rem 0 0;
  font-weight: 600;
  font-size: 0.875rem;
  color: var(--color-text-primary);
}

.skill-block__plan-meta {
  margin: 0.25rem 0 0;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}
</style>
