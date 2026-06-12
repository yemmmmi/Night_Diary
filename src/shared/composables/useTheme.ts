import { computed, ref, watch } from 'vue'

import { useSettingsStore } from '@/stores/settings'

export type ThemePreference = 'day' | 'night' | 'auto'
export type AppTheme = 'day' | 'night'

const theme = ref<AppTheme>('day')
let mediaQuery: MediaQueryList | null = null
let mediaListener: ((event: MediaQueryListEvent) => void) | null = null

function resolveTheme(preference: ThemePreference): AppTheme {
  if (preference === 'day' || preference === 'night') return preference
  if (typeof window === 'undefined') return 'day'
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'night' : 'day'
}

function applyTheme(value: AppTheme) {
  if (typeof document === 'undefined') return
  document.documentElement.setAttribute('data-theme', value)
  theme.value = value
}

function bindAutoThemeListener(preference: ThemePreference) {
  if (typeof window === 'undefined') return

  if (mediaQuery && mediaListener) {
    mediaQuery.removeEventListener('change', mediaListener)
    mediaQuery = null
    mediaListener = null
  }

  if (preference !== 'auto') return

  mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
  mediaListener = () => {
    applyTheme(resolveTheme('auto'))
  }
  mediaQuery.addEventListener('change', mediaListener)
}

function setThemePreference(preference: ThemePreference) {
  const settings = useSettingsStore()
  settings.load()
  settings.themePreference = preference
  applyTheme(resolveTheme(preference))
  bindAutoThemeListener(preference)
}

function setTheme(value: AppTheme) {
  setThemePreference(value)
}

function toggleTheme() {
  setThemePreference(theme.value === 'day' ? 'night' : 'day')
}

export function initTheme() {
  const settings = useSettingsStore()
  settings.load()
  const resolved = resolveTheme(settings.themePreference)
  applyTheme(resolved)
  bindAutoThemeListener(settings.themePreference)

  watch(
    () => settings.themePreference,
    (preference) => {
      applyTheme(resolveTheme(preference))
      bindAutoThemeListener(preference)
    },
  )
}

export function useTheme() {
  const settings = useSettingsStore()
  settings.load()

  const preference = computed({
    get: () => settings.themePreference,
    set: (value: ThemePreference) => setThemePreference(value),
  })

  return {
    theme,
    preference,
    setTheme,
    setThemePreference,
    toggleTheme,
  }
}
