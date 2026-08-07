<script setup lang="ts">
import { ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useDevStore } from '@/stores/dev'

const emit = defineEmits<{ switched: [] }>()

const authStore = useAuthStore()
const devStore = useDevStore()
const expanded = ref(false)
const switching = ref(false)
const error = ref<string | null>(null)

// 测试账号列表（密码统一 123456）
const TEST_ACCOUNTS = [
  { email: 'a@dev.test', nickname: 'Alice', label: '日记重度' },
  { email: 'b@dev.test', nickname: 'Bob', label: '对话重度' },
  { email: 'c@dev.test', nickname: 'Carol', label: '混合用户' },
  { email: 'd@dev.test', nickname: 'Dave', label: '边界/危机' },
  { email: 'e@dev.test', nickname: 'Eve', label: '轻度用户' },
]

async function switchTo(email: string) {
  if (switching.value) return
  switching.value = true
  expanded.value = false
  error.value = null
  try {
    await authStore.login(email, '123456')
    devStore.clearTraces()
    emit('switched')
  } catch (e) {
    error.value = e instanceof Error ? e.message : '切换失败'
  } finally {
    switching.value = false
  }
}
</script>

<template>
  <div class="account-switcher">
    <button
      class="account-switcher__button"
      :disabled="switching"
      @click="expanded = !expanded"
    >
      <span v-if="switching">切换中...</span>
      <span v-else>{{ authStore.user?.nickname || '切换账号' }}</span>
    </button>

    <div v-if="error" class="account-switcher__error">{{ error }}</div>

    <div v-if="expanded" class="account-switcher__dropdown">
      <button
        v-for="account in TEST_ACCOUNTS"
        :key="account.email"
        class="account-switcher__item"
        @click="switchTo(account.email)"
      >
        <span class="account-switcher__name">{{ account.nickname }}</span>
        <span class="account-switcher__label">{{ account.label }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.account-switcher {
  position: relative;
}
.account-switcher__button {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.25rem 0.625rem;
  border: 1px solid var(--color-border);
  border-radius: 0.375rem;
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
  font-size: 0.7rem;
  font-family: var(--font-ui);
  cursor: pointer;
  transition: border-color var(--motion-duration) var(--motion-ease);
}
.account-switcher__button:hover {
  border-color: var(--color-accent);
}
.account-switcher__button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.account-switcher__error {
  position: absolute;
  top: 100%;
  left: 0;
  margin-top: 0.25rem;
  padding: 0.25rem 0.5rem;
  background: var(--color-danger);
  color: var(--color-bg);
  font-size: 0.65rem;
  border-radius: 0.25rem;
  white-space: nowrap;
  z-index: 10;
}
.account-switcher__dropdown {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 0.25rem;
  min-width: 160px;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: 0.5rem;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  z-index: 100;
  overflow: hidden;
}
.account-switcher__item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  padding: 0.5rem 0.75rem;
  border: none;
  background: transparent;
  cursor: pointer;
  text-align: left;
  transition: background var(--motion-duration) var(--motion-ease);
}
.account-switcher__item:hover {
  background: var(--color-bg-elevated-2);
}
.account-switcher__name {
  font-size: 0.75rem;
  font-family: var(--font-ui);
  color: var(--color-text-primary);
}
.account-switcher__label {
  font-size: 0.65rem;
  color: var(--color-text-secondary);
}
</style>
