<script setup lang="ts">
withDefaults(
  defineProps<{
    elevated?: boolean
    blur?: boolean
    padding?: boolean
  }>(),
  {
    elevated: false,
    blur: false,
    padding: true,
  },
)
</script>

<template>
  <div
    class="glass-panel"
    :class="{
      'glass-panel--elevated': elevated,
      'glass-panel--blur': blur,
    }"
  >
    <div class="glass-panel__inner" :class="{ '!p-0': !padding }">
      <slot />
    </div>
  </div>
</template>
