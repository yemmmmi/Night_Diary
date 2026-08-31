<script setup lang="ts">
import { PhCaretRight } from '@phosphor-icons/vue'
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    id: string
    title: string
    subtitle?: string
    open?: boolean
  }>(),
  {
    subtitle: '',
    open: false,
  },
)

const emit = defineEmits<{
  toggle: [id: string]
}>()

const isOpen = computed(() => props.open)

function onToggle() {
  emit('toggle', props.id)
}
</script>

<template>
  <section class="settings-section" :class="{ 'is-open': isOpen }">
    <button type="button" class="settings-section__header" @click="onToggle">
      <div class="settings-section__titles">
        <h3 class="settings-section__title">{{ title }}</h3>
        <p v-if="subtitle" class="settings-section__subtitle">{{ subtitle }}</p>
      </div>
      <PhCaretRight :size="16" class="settings-section__chevron" :class="{ 'is-open': isOpen }" />
    </button>
    <div v-show="isOpen" class="settings-section__body">
      <slot />
    </div>
  </section>
</template>

<style scoped>
/* 细线分节：以一道线与标题分节，不用卡片边框阴影。 */
.settings-section {
  border-top: 1px solid var(--color-line);
  padding-top: 0.625rem;
}

.settings-section__header {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.25rem 0.125rem 0.75rem;
  border: none;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.settings-section__title {
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.settings-section__subtitle {
  margin-top: 0.25rem;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

.settings-section__chevron {
  color: var(--color-text-secondary);
  flex-shrink: 0;
  transition: transform var(--dur-fast) var(--ease-out-quart);
}

.settings-section__chevron.is-open {
  transform: rotate(90deg);
}

.settings-section__body {
  padding: 0 0.125rem 1.125rem;
}

/* 展开只动 opacity 与位移，不做高度过渡。 */
.settings-section.is-open .settings-section__body {
  animation: settings-section-reveal var(--dur-fast) var(--ease-out-quart) both;
}

@keyframes settings-section-reveal {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
