<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'

import { useTheme } from '@/shared/composables/useTheme'

const canvasRef = ref<HTMLCanvasElement | null>(null)
const { theme } = useTheme()

interface Particle {
  x: number
  y: number
  vx: number
  vy: number
  size: number
  alpha: number
}

let animationId = 0
let particles: Particle[] = []

function resizeCanvas(canvas: HTMLCanvasElement) {
  const dpr = window.devicePixelRatio || 1
  canvas.width = window.innerWidth * dpr
  canvas.height = window.innerHeight * dpr
  canvas.style.width = `${window.innerWidth}px`
  canvas.style.height = `${window.innerHeight}px`
  const ctx = canvas.getContext('2d')
  if (ctx) ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
}

function initParticles(count: number, width: number, height: number) {
  particles = Array.from({ length: count }, () => ({
    x: Math.random() * width,
    y: Math.random() * height,
    vx: (Math.random() - 0.5) * (theme.value === 'day' ? 0.35 : 0.15),
    vy: (Math.random() - 0.5) * (theme.value === 'day' ? 0.25 : 0.1),
    size: Math.random() * 2 + (theme.value === 'day' ? 1 : 0.5),
    alpha: Math.random() * 0.5 + 0.2,
  }))
}

function tick() {
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const width = window.innerWidth
  const height = window.innerHeight
  ctx.clearRect(0, 0, width, height)

  const primary = getComputedStyle(document.documentElement)
    .getPropertyValue('--particle-primary')
    .trim()
  const secondary = getComputedStyle(document.documentElement)
    .getPropertyValue('--particle-secondary')
    .trim()

  for (const p of particles) {
    p.x += p.vx
    p.y += p.vy
    if (p.x < 0) p.x = width
    if (p.x > width) p.x = 0
    if (p.y < 0) p.y = height
    if (p.y > height) p.y = 0

    ctx.beginPath()
    ctx.fillStyle = Math.random() > 0.7 ? secondary : primary
    ctx.globalAlpha = p.alpha
    ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2)
    ctx.fill()
  }

  ctx.globalAlpha = 1
  animationId = window.requestAnimationFrame(tick)
}

function start() {
  const canvas = canvasRef.value
  if (!canvas) return
  resizeCanvas(canvas)
  initParticles(theme.value === 'day' ? 32 : 24, window.innerWidth, window.innerHeight)
  cancelAnimationFrame(animationId)
  animationId = window.requestAnimationFrame(tick)
}

function onResize() {
  start()
}

onMounted(() => {
  start()
  window.addEventListener('resize', onResize)
})

onUnmounted(() => {
  cancelAnimationFrame(animationId)
  window.removeEventListener('resize', onResize)
})

watch(theme, () => {
  start()
})
</script>

<template>
  <canvas ref="canvasRef" class="particle-canvas" aria-hidden="true" />
</template>
