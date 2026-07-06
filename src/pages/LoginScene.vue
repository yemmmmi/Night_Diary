<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import BrandMark from '@/shared/components/BrandMark.vue'
import GameButton from '@/shared/components/GameButton.vue'
import GlassPanel from '@/shared/components/GlassPanel.vue'
import { useAuthStore } from '@/stores/auth'

type Mode = 'login' | 'register'

const router = useRouter()
const auth = useAuthStore()

const mode = ref<Mode>('login')
const email = ref('')
const password = ref('')
const nickname = ref('')
const showPassword = ref(false)
const loading = ref(false)
const error = ref('')
const successHint = ref('')

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

const isRegister = computed(() => mode.value === 'register')

const emailError = computed(() => {
  if (!email.value) return ''
  return EMAIL_RE.test(email.value) ? '' : '邮箱格式不正确'
})

const passwordError = computed(() => {
  if (!password.value) return ''
  return password.value.length >= 6 ? '' : '密码至少 6 个字符'
})

const formValid = computed(() => {
  if (!EMAIL_RE.test(email.value)) return false
  if (password.value.length < 6) return false
  return true
})

const submitLabel = computed(() => {
  if (loading.value) return '处理中…'
  return isRegister.value ? '注册并登录' : '登录'
})

function switchMode(next: Mode): void {
  if (mode.value === next) return
  mode.value = next
  error.value = ''
  successHint.value = ''
}

function resetFormState(): void {
  error.value = ''
  successHint.value = ''
}

async function handleSubmit(): Promise<void> {
  error.value = ''
  successHint.value = ''

  if (!EMAIL_RE.test(email.value)) {
    error.value = '请输入有效的邮箱地址'
    return
  }
  if (password.value.length < 6) {
    error.value = '密码至少需要 6 个字符'
    return
  }

  loading.value = true
  try {
    if (isRegister.value) {
      await auth.register(email.value, password.value, nickname.value || undefined)
      successHint.value = '注册成功，已为你自动登录'
    } else {
      await auth.login(email.value, password.value)
    }
    // 登录成功后跳转首页
    await router.replace('/')
  } catch (err) {
    error.value = err instanceof Error ? err.message : '操作失败，请重试'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <main class="login-scene">
    <GlassPanel elevated blur class="login-scene__card">
      <BrandMark class="login-scene__mark" />
      <h1 class="login-scene__title">夜记</h1>
      <p class="login-scene__subtitle">写下今天的心情，留待夜里慢慢回味</p>

      <div class="login-scene__tabs" role="tablist">
        <button
          type="button"
          role="tab"
          :aria-selected="mode === 'login'"
          class="login-scene__tab"
          :class="{ 'is-active': mode === 'login' }"
          @click="switchMode('login')"
        >
          登录
        </button>
        <button
          type="button"
          role="tab"
          :aria-selected="mode === 'register'"
          class="login-scene__tab"
          :class="{ 'is-active': mode === 'register' }"
          @click="switchMode('register')"
        >
          注册
        </button>
      </div>

      <form class="login-scene__form" novalidate @submit.prevent="handleSubmit">
        <label class="login-scene__field">
          <span class="login-scene__label">邮箱</span>
          <input
            v-model="email"
            type="email"
            autocomplete="email"
            placeholder="you@example.com"
            :disabled="loading"
            @input="resetFormState"
          />
          <span v-if="emailError" class="login-scene__hint login-scene__hint--error">
            {{ emailError }}
          </span>
        </label>

        <label class="login-scene__field">
          <span class="login-scene__label">密码</span>
          <div class="login-scene__password">
            <input
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              :autocomplete="isRegister ? 'new-password' : 'current-password'"
              placeholder="至少 6 个字符"
              :disabled="loading"
              @input="resetFormState"
            />
            <button
              type="button"
              class="login-scene__toggle"
              :aria-label="showPassword ? '隐藏密码' : '显示密码'"
              @click="showPassword = !showPassword"
            >
              {{ showPassword ? '隐藏' : '显示' }}
            </button>
          </div>
          <span v-if="passwordError" class="login-scene__hint login-scene__hint--error">
            {{ passwordError }}
          </span>
        </label>

        <label v-if="isRegister" class="login-scene__field">
          <span class="login-scene__label">昵称（可选）</span>
          <input
            v-model="nickname"
            type="text"
            autocomplete="nickname"
            maxlength="24"
            placeholder="例如：小夜"
            :disabled="loading"
          />
        </label>

        <p v-if="error" class="login-scene__error">{{ error }}</p>
        <p v-else-if="successHint" class="login-scene__success">{{ successHint }}</p>

        <GameButton
          type="submit"
          variant="primary"
          block
          :disabled="loading || !formValid"
          class="login-scene__submit"
        >
          {{ submitLabel }}
        </GameButton>
      </form>
    </GlassPanel>
  </main>
</template>

<style scoped>
.login-scene {
  min-height: calc(100vh - 2.5rem);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1.5rem 1rem;
}

.login-scene__card {
  width: min(28rem, 100%);
  padding: 2.25rem 1.75rem;
  text-align: center;
}

.login-scene__mark {
  width: 3rem;
  height: 3rem;
  margin: 0 auto 0.875rem;
}

.login-scene__title {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--color-text-primary);
  margin-bottom: 0.375rem;
  letter-spacing: 0.05em;
}

.login-scene__subtitle {
  font-size: 0.875rem;
  line-height: 1.6;
  color: var(--color-text-secondary);
  margin-bottom: 1.5rem;
}

.login-scene__tabs {
  display: flex;
  gap: 0.25rem;
  padding: 0.25rem;
  margin-bottom: 1.5rem;
  border-radius: 0.75rem;
  background: var(--color-bg-elevated-2);
  border: 1px solid var(--color-border);
}

.login-scene__tab {
  flex: 1;
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 0.625rem;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition:
    background-color var(--motion-duration) var(--motion-ease),
    color var(--motion-duration) var(--motion-ease);
}

.login-scene__tab:hover {
  color: var(--color-text-primary);
}

.login-scene__tab.is-active {
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
  box-shadow: 0 1px 3px color-mix(in srgb, var(--color-accent) 18%, transparent);
}

.login-scene__form {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  text-align: left;
}

.login-scene__field {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.login-scene__label {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
}

.login-scene__field input {
  width: 100%;
  padding: 0.625rem 0.75rem;
  border-radius: 0.625rem;
  border: 1px solid var(--color-border);
  background: var(--color-bg-elevated-2);
  color: var(--color-text-primary);
  font-size: 0.9375rem;
  transition: border-color var(--motion-duration) var(--motion-ease);
}

.login-scene__field input::placeholder {
  color: var(--color-text-secondary);
  opacity: 0.7;
}

.login-scene__field input:focus {
  outline: none;
  border-color: var(--color-accent);
}

.login-scene__field input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.login-scene__password {
  position: relative;
  display: flex;
  align-items: center;
}

.login-scene__password input {
  padding-right: 3.5rem;
}

.login-scene__toggle {
  position: absolute;
  right: 0.5rem;
  top: 50%;
  transform: translateY(-50%);
  padding: 0.25rem 0.5rem;
  border: none;
  border-radius: 0.5rem;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 0.75rem;
  cursor: pointer;
  transition: color var(--motion-duration) var(--motion-ease);
}

.login-scene__toggle:hover {
  color: var(--color-accent);
}

.login-scene__hint {
  font-size: 0.75rem;
  line-height: 1.4;
}

.login-scene__hint--error {
  color: var(--color-danger);
}

.login-scene__error {
  font-size: 0.8125rem;
  line-height: 1.5;
  color: var(--color-danger);
  background: color-mix(in srgb, var(--color-danger) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-danger) 25%, transparent);
  border-radius: 0.625rem;
  padding: 0.5rem 0.75rem;
  text-align: center;
}

.login-scene__success {
  font-size: 0.8125rem;
  line-height: 1.5;
  color: var(--color-success);
  background: color-mix(in srgb, var(--color-success) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-success) 25%, transparent);
  border-radius: 0.625rem;
  padding: 0.5rem 0.75rem;
  text-align: center;
}

.login-scene__submit {
  margin-top: 0.5rem;
}
</style>
