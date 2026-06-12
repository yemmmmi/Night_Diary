<script setup lang="ts">
import { PhCaretDown, PhCaretUp } from '@phosphor-icons/vue'
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
        <h2 class="settings-section__title">{{ title }}</h2>
        <p v-if="subtitle" class="settings-section__subtitle">{{ subtitle }}</p>
      </div>
      <PhCaretUp v-if="isOpen" :size="18" class="settings-section__chevron" />
      <PhCaretDown v-else :size="18" class="settings-section__chevron" />
    </button>
    <div v-show="isOpen" class="settings-section__body">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.settings-section {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-outer);
  background: var(--color-bg-elevated);
  overflow: hidden;
  transition: box-shadow var(--motion-duration) var(--motion-ease);
}

.settings-section.is-open {
  box-shadow: var(--shadow-panel, 0 4px 24px rgba(0, 0, 0, 0.06));
}

.settings-section__header {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 1rem 1.125rem;
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
}

.settings-section__body {
  padding: 0 1.125rem 1.125rem;
}
</style>
