<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

defineProps<{ frameless?: boolean }>()
import {
  PhNotebook,
  PhCalendarCheck,
  PhBrain,
  PhClockCounterClockwise,
  PhChatsCircle,
  PhCpu,
  PhGear,
} from '@phosphor-icons/vue'

const route = useRoute()
const router = useRouter()

interface Tab {
  key: string
  label: string
  icon: typeof PhNotebook
  routeName: string
}

const tabs: Tab[] = [
  { key: 'diary', label: '\u65e5\u8bb0', icon: PhNotebook, routeName: 'home' },
  { key: 'weekly', label: '\u5468\u8bb0', icon: PhCalendarCheck, routeName: 'weekly' },
  { key: 'memory', label: '\u8bb0\u5fc6\u5e93', icon: PhBrain, routeName: 'memory' },
  { key: 'review', label: '\u56de\u987e', icon: PhClockCounterClockwise, routeName: 'review' },
  { key: 'chat', label: '\u4f1a\u8bdd', icon: PhChatsCircle, routeName: 'chat' },
  { key: 'models', label: '\u6a21\u578b', icon: PhCpu, routeName: 'models' },
]

const activeKey = computed(() => {
  const name = route.name
  if (name === 'home') return 'diary'
  return (name as string) ?? 'diary'
})

function navigate(tab: Tab) {
  if (tab.routeName === 'home') {
    router.push('/')
  } else {
    router.push(`/${tab.routeName}`)
  }
}
</script>

<template>
  <nav class="nav-tabs" :class="{ 'nav-tabs--frameless': frameless }" role="tablist">
    <button
      v-for="tab in tabs"
      :key="tab.key"
      type="button"
      role="tab"
      class="nav-tabs__tab"
      :class="{ 'is-active': activeKey === tab.key }"
      :aria-selected="activeKey === tab.key"
      @click="navigate(tab)"
    >
      <component :is="tab.icon" :size="16" :weight="activeKey === tab.key ? 'fill' : 'regular'" />
      <span>{{ tab.label }}</span>
    </button>

    <RouterLink
      to="/settings"
      class="nav-tabs__settings"
      :class="{ 'is-active': route.name === 'settings' }"
      :aria-label="'\u8bbe\u7f6e'"
    >
      <PhGear :size="18" :weight="route.name === 'settings' ? 'fill' : 'regular'" />
    </RouterLink>
  </nav>
</template>

<style scoped>
.nav-tabs {
  display: flex;
  align-items: center;
  gap: 0.125rem;
  padding: 0.375rem 0.75rem;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg-elevated);
}

.nav-tabs__tab {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.4375rem 0.875rem;
  border: none;
  border-radius: 0.5rem;
  background: transparent;
  color: var(--color-text-secondary);
  font-family: var(--font-ui);
  font-size: 0.8125rem;
  font-weight: 500;
  cursor: pointer;
  transition:
    color var(--motion-duration) var(--motion-ease),
    background var(--motion-duration) var(--motion-ease);
}

.nav-tabs__tab:hover {
  color: var(--color-text-primary);
  background: var(--color-bg-elevated-2);
}

.nav-tabs__tab.is-active {
  color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 10%, transparent);
}

.nav-tabs__settings {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.125rem;
  height: 2.125rem;
  margin-left: auto;
  border-radius: 0.5rem;
  color: var(--color-text-secondary);
  transition:
    color var(--motion-duration) var(--motion-ease),
    background var(--motion-duration) var(--motion-ease);
}

.nav-tabs__settings:hover,
.nav-tabs__settings.is-active {
  color: var(--color-text-primary);
  background: var(--color-bg-elevated-2);
}

.nav-tabs--frameless {
  margin-top: 2.5rem;
}
</style>
