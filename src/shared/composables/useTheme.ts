import { ref } from 'vue'

export type AppTheme = 'day' | 'night'

const STORAGE_KEY = 'night-diary-theme'

const theme = ref<AppTheme>('day')

function resolveInitialTheme(): AppTheme {
  if (typeof window === 'undefined') return 'day'
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored === 'day' || stored === 'night') return stored
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'night' : 'day'
}

function applyTheme(value: AppTheme) {
  if (typeof document === 'undefined') return
  document.documentElement.setAttribute('data-theme', value)
  localStorage.setItem(STORAGE_KEY, value)
}

function setTheme(value: AppTheme) {
  theme.value = value
  applyTheme(value)
}

function toggleTheme() {
  setTheme(theme.value === 'day' ? 'night' : 'day')
}

export function initTheme() {
  const value = resolveInitialTheme()
  theme.value = value
  applyTheme(value)
}

export function useTheme() {
  return { theme, setTheme, toggleTheme }
}
