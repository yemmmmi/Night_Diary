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

  it('ignores legacy replier fields in stored settings', () => {
    localStorage.setItem(
      'night-diary-app-settings',
      JSON.stringify({
        onboardingCompleted: true,
        activeReplierId: 'preset-calm',
        userRepliers: [{ id: 'u1', type: 'user', name: 'x', persona: 'y' }],
      }),
    )
    const settings = useSettingsStore()
    settings.load()
    expect(settings.onboardingCompleted).toBe(true)
    expect((settings as unknown as Record<string, unknown>).setActiveReplier).toBeUndefined()
    expect((settings as unknown as Record<string, unknown>).replierName).toBeUndefined()
  })
})
