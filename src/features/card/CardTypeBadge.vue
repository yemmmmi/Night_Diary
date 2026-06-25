<script setup lang="ts">
import { cardTypeLabel } from '@/shared/utils/cardFormat'

defineProps<{
  cardType: string
}>()
</script>

<template>
  <span class="card-type-badge">{{ cardTypeLabel(cardType) }}</span>
</template>

<style scoped>
.card-type-badge {
  font-family: var(--font-ui);
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
  padding: 0.125rem 0.4375rem;
  background: var(--color-bg-elevated-2);
  border-radius: 0.375rem;
  white-space: nowrap;
}
</style>
