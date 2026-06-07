<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import gsap from 'gsap'

const route = useRoute()
const innerRef = ref<HTMLElement | null>(null)

const routeKey = computed(() => route.fullPath)

onMounted(() => {
  if (!innerRef.value) return
  gsap.fromTo(
    innerRef.value,
    { opacity: 0, y: 16, scale: 0.98 },
    {
      opacity: 1,
      y: 0,
      scale: 1,
      duration: 0.45,
      ease: 'power2.out',
    },
  )
})
</script>

<template>
  <Transition name="page" mode="out-in">
    <div ref="innerRef" :key="routeKey" class="page-transition">
      <slot />
    </div>
  </Transition>
</template>

<style scoped>
.page-transition {
  min-height: 100%;
}
</style>
