<script setup lang="ts">
/**
 * EmotionStamp — 情绪印章（规格 §4.4）：白字色块、3px 圆角、字距加宽。
 * 首次渲染播一次盖章动效（§7.2-1，280ms ease-stamp，落定 -2°）。
 * reduced-motion 下静止呈现（§7.3）。
 */
import { computed } from 'vue'

const props = defineProps<{ emotions: string[] }>()

const POSITIVE = new Set(['期待', '开心', '感激', '兴奋', '满足', '放松'])
const CALM = new Set(['平静', '安宁', '舒缓'])
const LOST = new Set(['迷茫', '困惑', '焦虑', '疲惫'])

function stampClass(emotion: string): string {
  if (POSITIVE.has(emotion)) return 'emotion-stamp--positive'
  if (CALM.has(emotion)) return 'emotion-stamp--calm'
  if (LOST.has(emotion)) return 'emotion-stamp--lost'
  return 'emotion-stamp--muted'
}

const list = computed(() => props.emotions.filter(Boolean))
</script>

<template>
  <div v-if="list.length" class="emotion-stamps">
    <span
      v-for="emotion in list"
      :key="emotion"
      data-testid="emotion-stamp"
      class="emotion-stamp"
      :class="stampClass(emotion)"
    >
      {{ emotion }}
    </span>
  </div>
</template>

<style scoped>
.emotion-stamps {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 0.375rem;
}

.emotion-stamp {
  display: inline-block;
  padding: 0.125rem 0.5rem;
  border-radius: 3px;
  font-size: 0.75rem;
  letter-spacing: 0.15em;
  color: #fff;
  transform: rotate(-2deg);
  animation: stamp-press 280ms var(--ease-stamp, cubic-bezier(0.34, 1.3, 0.64, 1)) both;
}

.emotion-stamp--positive {
  background: var(--color-seal-positive);
}

.emotion-stamp--calm {
  background: var(--color-seal-calm);
}

.emotion-stamp--lost {
  background: var(--color-seal-lost);
}

.emotion-stamp--muted {
  background: var(--color-seal-muted);
}

@keyframes stamp-press {
  0% {
    opacity: 0;
    transform: scale(1.4) rotate(0deg);
  }
  60% {
    opacity: 1;
    transform: scale(0.95) rotate(-2.5deg);
  }
  100% {
    opacity: 1;
    transform: scale(1) rotate(-2deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .emotion-stamp {
    animation: none;
  }
}
</style>
