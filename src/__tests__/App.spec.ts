import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { invoke } from '@tauri-apps/api/core'
import { createRouter, createMemoryHistory } from 'vue-router'

import App from '../App.vue'
import HomeScene from '../pages/HomeScene.vue'

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}))

vi.mock('@tauri-apps/api/window', () => ({
  getCurrentWindow: () => ({
    minimize: vi.fn(),
    maximize: vi.fn(),
    unmaximize: vi.fn(),
    isMaximized: vi.fn().mockResolvedValue(false),
    close: vi.fn(),
  }),
}))

vi.mock('@/shared/api/diary', () => ({
  listDiaryEntries: vi.fn().mockResolvedValue([]),
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

describe('App', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('__TAURI_INTERNALS__', {})
    vi.mocked(invoke).mockImplementation((cmd: string) => {
      if (cmd === 'get_backend_port') {
        return Promise.resolve(18000)
      }
      if (cmd === 'is_backend_ready' || cmd === 'check_backend_health') {
        return Promise.resolve(true)
      }
      return Promise.reject(new Error(`unexpected: ${cmd}`))
    })
  })

  it('shows loading then ready state', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: HomeScene },
        { path: '/design-system', component: HomeScene },
        { path: '/settings', component: HomeScene },
      ],
    })
    const wrapper = mount(App, {
      global: { plugins: [createPinia(), router] },
    })
    expect(wrapper.text()).toContain('正在连接 AI 引擎')

    await flushPromises()
    await router.isReady()
    expect(wrapper.text()).toContain('夜记')
    expect(wrapper.text()).toContain('写日记')
  })
})
