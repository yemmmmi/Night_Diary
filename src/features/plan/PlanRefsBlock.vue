<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { PhArrowSquareOut } from '@phosphor-icons/vue'

import { planCopy } from '@/shared/copy/plan'
import type { SourceRef } from '@/shared/api/plan'

const props = defineProps<{ refs: SourceRef[] }>()

const router = useRouter()

const diaryRefs = computed(() => props.refs.filter((r) => r.type === 'diary'))

function shortDate(iso: string): string {
  const [, m, d] = iso.split('-')
  return `${Number(m)}/${Number(d)}`
}

function openRef(ref: SourceRef) {
  router.push(`/write/${ref.id}`)
}
</script>

<template>
  <blockquote v-if="diaryRefs.length > 0" class="plan-refs">
    <p class="plan-refs__label">{{ planCopy.refsLabel }}</p>
    <div v-for="(ref, i) in diaryRefs" :key="i" class="plan-refs__row">
      <span v-if="ref.snippet" class="plan-refs__snippet">{{ ref.snippet }}</span>
      <button v-if="ref.date" type="button" class="plan-refs__date" @click="openRef(ref)">
        {{ shortDate(ref.date) }} <PhArrowSquareOut :size="11" />
      </button>
    </div>
  </blockquote>
</template>

<style scoped>
.plan-refs {
  margin: 8px 0;
  padding: 8px 12px;
  border-left: 2px solid var(--color-accent, #d4a574);
  background: color-mix(in srgb, var(--color-accent) 6%, transparent);
  border-radius: 0 8px 8px 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.plan-refs__label {
  margin: 0;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--color-text-secondary, #71717a);
}
.plan-refs__row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 13px;
}
.plan-refs__snippet {
  color: var(--color-text-primary);
  flex: 1;
}
.plan-refs__date {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  border: none;
  background: transparent;
  color: var(--color-accent, #d4a574);
  font-size: 12px;
  cursor: pointer;
  padding: 0;
  white-space: nowrap;
}
.plan-refs__date:hover {
  text-decoration: underline;
}
</style>
