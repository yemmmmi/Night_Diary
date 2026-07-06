import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { getHttpClient } from '@/shared/api/http'
import { formatApiError } from '@/shared/utils/apiError'

const TOKEN_STORAGE_KEY = 'night_diary_token'

export interface UserResponse {
  id: number
  email: string
  nickname: string
  is_active: boolean
  created_at: string
}

interface TokenResponse {
  access_token: string
  token_type: string
  user: UserResponse
}

interface RegisterPayload {
  email: string
  password: string
  nickname?: string
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(readTokenFromStorage())
  const user = ref<UserResponse | null>(null)

  const isAuthenticated = computed<boolean>(() => token.value !== null && token.value.length > 0)

  function readTokenFromStorage(): string | null {
    if (typeof window === 'undefined') return null
    try {
      const value = localStorage.getItem(TOKEN_STORAGE_KEY)
      return value && value.length > 0 ? value : null
    } catch {
      return null
    }
  }

  function setToken(value: string | null): void {
    token.value = value
    if (typeof window === 'undefined') return
    if (value && value.length > 0) {
      localStorage.setItem(TOKEN_STORAGE_KEY, value)
    } else {
      localStorage.removeItem(TOKEN_STORAGE_KEY)
    }
  }

  function getToken(): string | null {
    return readTokenFromStorage()
  }

  function setUser(value: UserResponse | null): void {
    user.value = value
  }

  async function login(email: string, password: string): Promise<UserResponse> {
    const client = await getHttpClient()
    const formData = new URLSearchParams()
    formData.append('username', email)
    formData.append('password', password)

    let response
    try {
      response = await client.post<TokenResponse>('/api/v1/auth/login', formData, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      })
    } catch (err) {
      throw new Error(formatApiError(err, '登录失败'))
    }

    const payload = response.data
    if (!payload.access_token) {
      throw new Error('登录失败：服务端未返回有效令牌')
    }

    setToken(payload.access_token)
    setUser(payload.user)
    return payload.user
  }

  async function register(email: string, password: string, nickname?: string): Promise<UserResponse> {
    const payload: RegisterPayload = { email, password }
    if (nickname && nickname.trim().length > 0) {
      payload.nickname = nickname.trim()
    }

    const client = await getHttpClient()
    try {
      await client.post<UserResponse>('/api/v1/auth/register', payload)
    } catch (err) {
      throw new Error(formatApiError(err, '注册失败'))
    }

    // 注册成功后自动登录
    return await login(email, password)
  }

  async function fetchUser(): Promise<UserResponse | null> {
    const storedToken = getToken()
    if (!storedToken) {
      setUser(null)
      return null
    }

    // 保证 store 内 token 与 localStorage 一致
    if (token.value !== storedToken) {
      token.value = storedToken
    }

    const client = await getHttpClient()
    try {
      const response = await client.get<UserResponse>('/api/v1/auth/me')
      setUser(response.data)
      return response.data
    } catch (err) {
      // 令牌失效时清理本地状态，避免循环触发 401
      const message = formatApiError(err, '获取用户信息失败')
      if (message.includes('401') || message.includes('未授权')) {
        clearLocalState()
      }
      throw new Error(message)
    }
  }

  function clearLocalState(): void {
    setToken(null)
    setUser(null)
  }

  function logout(): void {
    clearLocalState()
    // 跳转登录页：与 http.ts 401 拦截器保持一致的 hash 路由方式
    if (typeof window !== 'undefined' && !window.location.hash.includes('/login')) {
      window.location.hash = '#/login'
    }
  }

  return {
    token,
    user,
    isAuthenticated,
    setToken,
    getToken,
    login,
    register,
    fetchUser,
    logout,
  }
})
