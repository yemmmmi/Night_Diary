<script setup lang="ts">
import { computed, ref } from 'vue'
import { PhCaretDown, PhGearFine } from '@phosphor-icons/vue'

import type { ProcessInfo } from '@/shared/api/conversation'
import { chatCopy } from '@/shared/copy/chat'

const props = defineProps<{
  info: ProcessInfo
}>()

const open = ref(false)

const SKILL_LABELS: Record<string, string> = {
  record: '记录',
  insight: '洞悉',
  plan: '计划',
}

const INTENT_LABELS: Record<string, string> = {
  casual_chat: '日常闲聊',
  emotional_vent: '情绪倾诉',
  retrospective_query: '回顾查询',
  advice_seeking: '寻求建议',
  crisis_signal: '危机信号',
  entity_query: '实体查询',
  plan_exploration: '计划探讨',
  task_command: '任务指令',
}

const skillLabel = computed(() => {
  const skill = props.info.skill
  if (!skill) return ''
  return SKILL_LABELS[skill] ?? skill
})

const intentLabel = computed(() => {
  const intent = props.info.intent ?? ''
  if (intent.startsWith('user_skill_')) {
    const name = intent.slice('user_skill_'.length)
    return `技能直达 · ${SKILL_LABELS[name] ?? name}`
  }
  return INTENT_LABELS[intent] ?? intent
})

const toolCalls = computed(() => props.info.tool_calls ?? [])

const seconds = computed(() => {
  const ms = props.info.duration_ms ?? 0
  return Math.round(ms / 100) / 10
})

const toggleText = computed(() =>
  chatCopy.processToggle(skillLabel.value || props.info.skill, toolCalls.value.length, seconds.value),
)

const retrievalText = computed(() => {
  const parts: string[] = []
  const diaries = props.info.retrieved_diaries ?? 0
  const memories = props.info.retrieved_memories ?? 0
  if (diaries > 0) parts.push(chatCopy.processRetrievalDiaries(diaries))
  if (memories > 0) parts.push(chatCopy.processRetrievalMemories(memories))
  return parts.join(' · ')
})

const tokens = computed(() => props.info.tokens ?? 0)
</script>

<template>
  <div class="process" data-testid="letter-process">
    <button
      type="button"
      class="process__toggle"
      :aria-expanded="open"
      data-testid="letter-process-toggle"
      @click="open = !open"
    >
      <PhGearFine :size="12" aria-hidden="true" />
      {{ toggleText }}
      <PhCaretDown :size="11" aria-hidden="true" :class="{ 'is-open': open }" />
    </button>

    <dl v-if="open" class="process__detail" data-testid="letter-process-detail">
      <div class="process__row">
        <dt>{{ chatCopy.processIntentLabel }}</dt>
        <dd>{{ intentLabel }}</dd>
      </div>
      <div v-if="skillLabel" class="process__row">
        <dt>{{ chatCopy.processSkillLabel }}</dt>
        <dd>
          {{ skillLabel }}
          <span class="process__tag">
            {{ info.skill_source === 'manual' ? chatCopy.processSkillManual : chatCopy.processSkillAuto }}
          </span>
        </dd>
      </div>
      <div v-if="toolCalls.length > 0" class="process__row">
        <dt>{{ chatCopy.processToolsLabel }}</dt>
        <dd>
          <span v-for="call in toolCalls" :key="call.name" class="process__tool">
            <span class="process__tool-name">{{ call.name }}</span>
            <span class="process__tag" :class="{ 'process__tag--mcp': call.source === 'mcp' }">
              {{ call.source === 'mcp' ? chatCopy.processToolSourceMcp : chatCopy.processToolSourceLocal }}
            </span>
          </span>
        </dd>
      </div>
      <div v-if="retrievalText" class="process__row">
        <dt>{{ chatCopy.processRetrievalLabel }}</dt>
        <dd>{{ retrievalText }}</dd>
      </div>
      <div v-if="seconds > 0 || tokens > 0" class="process__row">
        <dt>{{ chatCopy.processDurationLabel }}</dt>
        <dd>
          {{ seconds > 0 ? `${seconds}s` : '' }}
          <template v-if="tokens > 0"> · {{ chatCopy.processTokensLabel }} {{ tokens.toLocaleString() }}</template>
        </dd>
      </div>
    </dl>
  </div>
</template>

<style scoped>
/* 执行过程：默认收成一行小字（安静原则），展开后是定义列表 */
.process {
  margin-top: 0.5rem;
}

.process__toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  border: none;
  background: none;
  padding: 0;
  font-size: 0.6875rem;
  color: var(--color-text-faint);
  cursor: pointer;
}

.process__toggle:hover {
  color: var(--color-text-secondary);
}

.process__toggle .is-open {
  transform: rotate(180deg);
}

.process__detail {
  margin: 0.375rem 0 0;
  padding: 0.375rem 0.625rem;
  border: 1px solid var(--color-line);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.process__row {
  display: flex;
  gap: 0.5rem;
  font-size: 0.6875rem;
  line-height: 1.6;
}

.process__row dt {
  flex: 0 0 auto;
  color: var(--color-text-faint);
}

.process__row dd {
  margin: 0;
  color: var(--color-text-secondary);
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.3rem;
}

.process__tool {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
}

.process__tool-name {
  font-family: var(--font-mono, monospace);
}

.process__tag {
  padding: 0 0.3rem;
  border: 1px solid var(--color-line);
  border-radius: 4px;
  font-size: 0.625rem;
  color: var(--color-text-faint);
}

.process__tag--mcp {
  border-color: color-mix(in srgb, var(--color-accent) 40%, var(--color-line));
  color: var(--color-accent);
}
</style>
