<script setup lang="ts">
/**
 * MoodTrendChart — 近 N 天情绪均值细柱图（规格 §5.4，自绘，弃用 ECharts）。
 * 数据源是服务端 getMoodTrends：只返回有卡片的日期，这里补零成连续 N 天格。
 * 柱高只用 transform: scaleY 表达（transform-only 动效红线）；
 * 入场逐根生长（bar-grow + 40ms stagger）由 motion.css 的 .trend-bars--enter 提供，
 * 只随「进入动作」播放一次：onMounted 挂类，onActivated 先摘再挂以重触发 reflow。
 */
import { computed, nextTick, onActivated, onMounted, ref } from 'vue'

import type { MoodTrendPoint } from '@/shared/api/card'
import { toIsoDate } from '@/shared/utils/diaryFormat'

const props = withDefaults(
  defineProps<{
    points: MoodTrendPoint[]
    days?: number
  }>(),
  {
    days: 14,
  },
)

interface TrendBar {
  date: string
  avgMood: number
  cardCount: number
  scale: number
}

function clamp01(value: number): number {
  if (!Number.isFinite(value)) return 0
  return Math.min(1, Math.max(0, value))
}

/** 补零：把零散的服务端点拉成「今天往前 N 天」的连续格，升序排列。 */
function buildBars(points: MoodTrendPoint[], days: number): TrendBar[] {
  const byDate = new Map<string, MoodTrendPoint>()
  for (const point of points) byDate.set(point.date, point)

  const bars: TrendBar[] = []
  const today = new Date()
  for (let offset = days - 1; offset >= 0; offset -= 1) {
    const day = new Date(today.getFullYear(), today.getMonth(), today.getDate() - offset)
    const iso = toIsoDate(day)
    const point = byDate.get(iso)
    const avgMood = point?.avg_mood ?? 0
    bars.push({
      date: iso,
      avgMood,
      cardCount: point?.card_count ?? 0,
      scale: Math.round(clamp01(avgMood) * 1000) / 1000,
    })
  }
  return bars
}

const bars = computed<TrendBar[]>(() => buildBars(props.points, props.days))

/** 首个数据集到达才落 DOM：细柱带着最终 --bar-scale 插入，生长动效一次到位。 */
const hasPoints = computed(() => props.points.length > 0)

/** 悬停原生 title：日期 · 均值 x · n 张（安静，无 tooltip 组件）。 */
function barTitle(bar: TrendBar): string {
  return `${bar.date} · 均值 ${bar.avgMood.toFixed(2)} · ${bar.cardCount} 张`
}

function barStyle(bar: TrendBar, index: number): Record<string, string> {
  return {
    '--i': String(index),
    '--bar-scale': String(bar.scale),
    transform: `scaleY(${bar.scale})`,
  }
}

const axisStart = computed(() => bars.value[0]?.date.slice(5) ?? '')
const axisEnd = computed(() => bars.value[bars.value.length - 1]?.date.slice(5) ?? '')
const ariaLabel = computed(() => `近 ${props.days} 天情绪均值细柱图`)

const entered = ref(false)

onMounted(() => {
  entered.value = true
})

onActivated(async () => {
  entered.value = false
  await nextTick()
  entered.value = true
})
</script>

<template>
  <div v-if="hasPoints" class="trend-chart">
    <div
      class="trend-bars"
      :class="{ 'trend-bars--enter': entered }"
      role="img"
      :aria-label="ariaLabel"
    >
      <div
        v-for="(bar, index) in bars"
        :key="bar.date"
        class="trend-bar"
        data-testid="trend-bar"
        :title="barTitle(bar)"
        :style="barStyle(bar, index)"
      />
    </div>
    <div class="trend-chart__axis" aria-hidden="true">
      <span>{{ axisStart }}</span>
      <span>{{ axisEnd }}</span>
    </div>
  </div>
</template>

<style scoped>
.trend-chart {
  width: 100%;
}

/* 细柱行：底部一条账簿基线，每根柱是一个等宽格，柱身是格内 3px 细条 */
.trend-bars {
  display: flex;
  align-items: stretch;
  gap: 2px;
  height: 6rem;
  padding-bottom: 0.25rem;
  border-bottom: 1px solid var(--color-line);
}

.trend-bar {
  position: relative;
  flex: 1 1 0;
  min-width: 0;
  transform-origin: bottom;
}

/* 悬停命中区是整格，可见的只是居中细柱 */
.trend-bar::after {
  content: '';
  position: absolute;
  left: 50%;
  bottom: 0;
  width: 3px;
  height: 100%;
  margin-left: -1.5px;
  border-radius: 1px;
  background: var(--color-accent);
  opacity: 0.85;
}

.trend-chart__axis {
  display: flex;
  justify-content: space-between;
  margin-top: 0.375rem;
  font-size: 0.6875rem;
  color: var(--color-text-faint);
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.04em;
}
</style>
