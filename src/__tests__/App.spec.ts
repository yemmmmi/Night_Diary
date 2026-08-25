import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { createRouter, createMemoryHistory } from 'vue-router'

import App from '../App.vue'
import TimelineScene from '../pages/TimelineScene.vue'

vi.mock('@/shared/api/diary', () => ({
  listDiaryEntries: vi.fn().mockResolvedValue([{ id: 1 }]),
}))

vi.mock('@/shared/api/stats', () => ({
  getStats: vi.fn().mockResolvedValue({
    diary_count: 0,
    analysis_count: 0,
    total_token_cost: 0,
    llm_call_count: 0,
    total_tokens_in: 0,
    total_tokens_out: 0,
  }),
}))

vi.mock('axios', () => {
  const interceptors = {
    request: { use: vi.fn() },
    response: { use: vi.fn() },
  }
  return {
    default: {
      create: vi.fn(() => ({ get: vi.fn(), post: vi.fn(), interceptors })),
    },
    isAxiosError: () => false,
  }
})

describe('App', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.setItem(
      'night-diary-app-settings',
      JSON.stringify({ onboardingCompleted: true, themePreference: 'auto' }),
    )
    localStorage.setItem('night_diary_token', 'fake-token')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200 }))
  })

  it('shows shell immediately then connects to backend', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', name: 'home', component: TimelineScene },
        { path: '/settings', name: 'settings', component: TimelineScene },
      ],
    })
    const wrapper = mount(App, {
      global: { plugins: [createPinia(), router] },
    })
    await router.isReady()
    await flushPromises()
    expect(wrapper.text()).toContain('记一笔')
  })
})
