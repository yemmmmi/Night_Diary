<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { MemoryCard } from '@/shared/api/card'
import {
  buildMoodTrendPoints,
  MOOD_TREND_DEFAULT_DAYS,
  moodLevelLabel,
  type MoodTrendPoint,
} from '@/shared/utils/moodTrend'

const props = withDefaults(
  defineProps<{
    cards: MemoryCard[]
    days?: number
    title?: string
    description?: string
  }>(),
  {
    days: MOOD_TREND_DEFAULT_DAYS,
  },
)

const chartEl = ref<HTMLDivElement | null>(null)
/* eslint-disable-next-line @typescript-eslint/no-explicit-any */
let chartInstance: any = null

const points = computed(() => buildMoodTrendPoints(props.cards, props.days))
const canRender = computed(() => points.value.length >= 2)

function formatTooltip(point: MoodTrendPoint): string {
  const dateLabel = point.date.slice(5).replace('-', '/')
  const moodText = moodLevelLabel(point.avgMood)
  const emotionText =
    point.emotions.length > 0 ? point.emotions.join('、') : '未标注'
  const countHint =
    point.cardCount > 1 ? `<br/>${point.cardCount} 条记录` : ''
  return `${dateLabel}<br/>心情：${emotionText}<br/>程度：${moodText}${countHint}`
}

function renderChart() {
  if (!chartEl.value || !canRender.value) return
  /* eslint-disable-next-line @typescript-eslint/no-explicit-any */
  const echarts = (window as any).echarts
  if (!echarts) return

  const style = getComputedStyle(document.documentElement)
  const accent = style.getPropertyValue('--color-accent').trim() || '#D4A574'
  const muted = style.getPropertyValue('--color-text-secondary').trim() || '#7A6F63'
  const rule = style.getPropertyValue('--color-border').trim() || 'rgba(61,52,41,0.12)'

  if (chartInstance) chartInstance.dispose()

  chartInstance = echarts.init(chartEl.value, null, { renderer: 'svg' })
  chartInstance.setOption({
    animation: false,
    grid: { top: 12, right: 16, bottom: 28, left: 40 },
    xAxis: {
      type: 'category',
      data: points.value.map((p) => p.date.slice(5)),
      axisLine: { lineStyle: { color: rule } },
      axisLabel: { color: muted, fontSize: 10 },
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 1,
      interval: 0.25,
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: rule } },
      axisLabel: {
        color: muted,
        fontSize: 10,
        formatter: (v: number) => (v === 0 ? '低' : v === 1 ? '高' : ''),
      },
    },
    series: [
      {
        type: 'line',
        data: points.value.map((p) => p.avgMood),
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { color: accent, width: 2 },
        itemStyle: { color: accent },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: `${accent}33` },
              { offset: 1, color: `${accent}00` },
            ],
          },
        },
      },
    ],
    tooltip: {
      trigger: 'axis',
      appendToBody: true,
      /* eslint-disable-next-line @typescript-eslint/no-explicit-any */
      formatter: (params: any) => {
        const index = params[0]?.dataIndex
        if (typeof index !== 'number' || !points.value[index]) return ''
        return formatTooltip(points.value[index])
      },
    },
  })
}

function disposeChart() {
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
}

function onResize() {
  chartInstance?.resize()
}

watch(
  () => [props.cards, props.days] as const,
  async () => {
    await nextTick()
    if (canRender.value) renderChart()
    else disposeChart()
  },
  { deep: true },
)

onMounted(async () => {
  await nextTick()
  renderChart()
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  disposeChart()
})
</script>

<template>
  <section v-if="canRender" class="mood-trend-chart">
    <header v-if="title || description" class="mood-trend-chart__header">
      <p v-if="title" class="mood-trend-chart__title">{{ title }}</p>
      <p v-if="description" class="mood-trend-chart__desc">{{ description }}</p>
    </header>
    <div ref="chartEl" class="mood-trend-chart__canvas" />
  </section>
</template>

<style scoped>
.mood-trend-chart {
  padding: 1rem;
}

.mood-trend-chart__header {
  margin-bottom: 0.5rem;
}

.mood-trend-chart__title {
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 0.25rem;
}

.mood-trend-chart__desc {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

.mood-trend-chart__canvas {
  width: 100%;
  height: 220px;
}
</style>
