import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { useSettingsStore } from '@/stores/settings'

describe('settings store', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('loads defaults when storage is empty', () => {
    const store = useSettingsStore()
    store.load()
    expect(store.onboardingCompleted).toBe(false)
    expect(store.themePreference).toBe('auto')
    expect(store.soundEnabled).toBe(false)
  })

  it('persists onboarding completion', () => {
    const store = useSettingsStore()
    store.load()
    store.completeOnboarding()
    const raw = localStorage.getItem('night-diary-app-settings')
    expect(raw).toContain('"onboardingCompleted":true')
  })
})
