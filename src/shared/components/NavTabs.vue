<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

defineProps<{ frameless?: boolean }>()
import { PhCpu, PhGear, PhTerminal } from '@phosphor-icons/vue'
import { useSettingsStore } from '@/stores/settings'

const route = useRoute()
const router = useRouter()
const settings = useSettingsStore()

interface Tab {
  key: string
  label: string
  routeName: string
  path: string
}

const tabs: Tab[] = [
  { key: 'today', label: '今天', routeName: 'home', path: '/' },
  { key: 'record', label: '记录', routeName: 'timeline', path: '/timeline' },
  { key: 'plan', label: '规划', routeName: 'plan', path: '/plan' },
  { key: 'memory', label: '洞悉', routeName: 'memory', path: '/memory' },
  { key: 'chat', label: '笔谈', routeName: 'chat', path: '/chat' },
]

const activeKey = computed(() => {
  const tab = tabs.find((t) => t.routeName === route.name)
  return tab?.key ?? ''
})

const gearActive = computed(
  () => route.name === 'models' || route.name === 'settings',
)

function navigate(tab: Tab) {
  router.push(tab.path)
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
      {{ tab.label }}
    </button>

    <div class="nav-tabs__gear">
      <RouterLink
        v-if="settings.developerMode"
        to="/dev"
        class="nav-tabs__icon"
        :class="{ 'is-active': route.name === 'dev' }"
        aria-label="开发者"
      >
        <PhTerminal :size="17" :weight="route.name === 'dev' ? 'fill' : 'regular'" />
      </RouterLink>

      <RouterLink
        to="/models"
        class="nav-tabs__icon"
        :class="{ 'is-active': route.name === 'models' }"
        aria-label="模型"
      >
        <PhCpu :size="17" :weight="route.name === 'models' ? 'fill' : 'regular'" />
      </RouterLink>

      <RouterLink
        to="/settings"
        class="nav-tabs__icon"
        :class="{ 'is-active': gearActive && route.name === 'settings' }"
        aria-label="设置"
      >
        <PhGear :size="17" :weight="route.name === 'settings' ? 'fill' : 'regular'" />
      </RouterLink>
    </div>
  </nav>
</template>

<style scoped>
.nav-tabs {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0 1rem;
  border-bottom: 1px solid var(--color-line);
  background: var(--color-bg);
}

.nav-tabs__tab {
  position: relative;
  border: none;
  background: transparent;
  padding: 0.75rem 0.875rem;
  color: var(--color-text-secondary);
  font-family: var(--font-ui);
  font-size: 0.8125rem;
  font-weight: 500;
  letter-spacing: 0.08em;
  cursor: pointer;
  transition: color var(--dur-fast) var(--ease-out-quart);
}

.nav-tabs__tab::after {
  content: '';
  position: absolute;
  left: 0.875rem;
  right: 0.875rem;
  bottom: -1px;
  height: 2px;
  background: var(--color-accent);
  transform: scaleX(0);
  transform-origin: left;
  transition: transform var(--dur-fast) var(--ease-out-quart);
}

.nav-tabs__tab:hover {
  color: var(--color-text-primary);
}

.nav-tabs__tab.is-active {
  color: var(--color-accent);
}

.nav-tabs__tab.is-active::after {
  transform: scaleX(1);
}

.nav-tabs__gear {
  display: inline-flex;
  align-items: center;
  gap: 0.125rem;
  margin-left: auto;
}

.nav-tabs__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  border-radius: var(--radius-button);
  color: var(--color-text-secondary);
  transition:
    color var(--dur-fast) var(--ease-out-quart),
    background var(--dur-fast) var(--ease-out-quart);
}

.nav-tabs__icon:hover,
.nav-tabs__icon.is-active {
  color: var(--color-text-primary);
  background: var(--color-bg-elevated-2);
}

.nav-tabs--frameless {
  margin-top: 2.5rem;
}
</style>
