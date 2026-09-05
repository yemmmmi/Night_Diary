import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

import type { ThemePreference } from '@/shared/composables/useTheme'

const STORAGE_KEY = 'night-diary-app-settings'

export interface AppSettingsSnapshot {
  nickname: string
  themePreference: ThemePreference
  soundEnabled: boolean
  onboardingCompleted: boolean
  developerMode: boolean
}

const DEFAULTS: AppSettingsSnapshot = {
  nickname: '',
  themePreference: 'auto',
  soundEnabled: false,
  onboardingCompleted: false,
  developerMode: false,
}

function readStored(): AppSettingsSnapshot {
  if (typeof window === 'undefined') return { ...DEFAULTS }
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { ...DEFAULTS }
    const parsed = JSON.parse(raw) as Partial<AppSettingsSnapshot>
    return {
      nickname: typeof parsed.nickname === 'string' ? parsed.nickname : DEFAULTS.nickname,
      themePreference:
        parsed.themePreference === 'day' ||
        parsed.themePreference === 'night' ||
        parsed.themePreference === 'auto'
          ? parsed.themePreference
          : DEFAULTS.themePreference,
      soundEnabled: Boolean(parsed.soundEnabled),
      onboardingCompleted: Boolean(parsed.onboardingCompleted),
      developerMode: Boolean(parsed.developerMode),
    }
  } catch {
    return { ...DEFAULTS }
  }
}

export const useSettingsStore = defineStore('settings', () => {
  const loaded = ref(false)
  const nickname = ref(DEFAULTS.nickname)
  const themePreference = ref<ThemePreference>(DEFAULTS.themePreference)
  const soundEnabled = ref(DEFAULTS.soundEnabled)
  const onboardingCompleted = ref(DEFAULTS.onboardingCompleted)
  const developerMode = ref(DEFAULTS.developerMode)

  function applySnapshot(snapshot: AppSettingsSnapshot) {
    nickname.value = snapshot.nickname
    themePreference.value = snapshot.themePreference
    soundEnabled.value = snapshot.soundEnabled
    onboardingCompleted.value = snapshot.onboardingCompleted
    developerMode.value = snapshot.developerMode
  }

  function load() {
    if (loaded.value) return
    applySnapshot(readStored())
    loaded.value = true
  }

  function persist() {
    const snapshot: AppSettingsSnapshot = {
      nickname: nickname.value,
      themePreference: themePreference.value,
      soundEnabled: soundEnabled.value,
      onboardingCompleted: onboardingCompleted.value,
      developerMode: developerMode.value,
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot))
  }

  function completeOnboarding() {
    onboardingCompleted.value = true
    persist()
  }

  watch(
    [nickname, themePreference, soundEnabled, onboardingCompleted, developerMode],
    persist,
    { deep: true },
  )

  return {
    loaded,
    nickname,
    themePreference,
    soundEnabled,
    onboardingCompleted,
    developerMode,
    load,
    persist,
    completeOnboarding,
  }
})
