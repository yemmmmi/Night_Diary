<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { MoodTrendPoint } from '@/shared/api/card'

const props = defineProps<{ points: MoodTrendPoint[] }>()

const chartEl = ref<HTMLDivElement | null>(null)
/* eslint-disable-next-line @typescript-eslint/no-explicit-any */
let chartInstance: any = null

function render() {
  if (!chartEl.value || props.points.length === 0) return
  /* eslint-disable-next-line @typescript-eslint/no-explicit-any */
  const echarts = (window as any).echarts
  if (!echarts) return

  const style = getComputedStyle(document.documentElement)
  const accent = style.getPropertyValue('--color-accent').trim() || '#D4A574'
  const muted = style.getPropertyValue('--color-text-secondary').trim() || '#7A6F63'

  if (chartInstance) chartInstance.dispose()
  chartInstance = echarts.init(chartEl.value, null, { renderer: 'svg' })
  chartInstance.setOption({
    animation: false,
    grid: { top: 6, right: 4, bottom: 18, left: 4 },
    xAxis: {
      type: 'category',
      data: props.points.map((p) => p.date.slice(5)),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: muted, fontSize: 9, interval: 2 },
    },
    yAxis: { type: 'value', show: false, min: 0, max: 1 },
    series: [
      {
        type: 'line',
        data: props.points.map((p) => p.avg_mood),
        smooth: true,
        symbol: 'circle',
        symbolSize: 4,
        lineStyle: { color: accent, width: 1.5 },
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
        if (typeof index !== 'number' || !props.points[index]) return ''
        const p = props.points[index]
        return `${p.date} · ${p.card_count} 张卡片`
      },
    },
  })
}

onMounted(render)
watch(() => props.points, render)
onBeforeUnmount(() => {
  if (chartInstance) chartInstance.dispose()
  chartInstance = null
})
</script>

<template>
  <div v-if="points.length > 0" ref="chartEl" class="week-mood-chart" />
</template>

<style scoped>
.week-mood-chart {
  width: 100%;
  height: 3.5rem;
}
</style>
