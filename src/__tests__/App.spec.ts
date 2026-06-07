import { mount, flushPromises } from '@vue/test-utils'
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
      global: { plugins: [router] },
    })
    expect(wrapper.text()).toContain('正在连接 AI 引擎')

    await flushPromises()
    await router.isReady()
    expect(wrapper.text()).toContain('夜记')
    expect(wrapper.text()).toContain('http://127.0.0.1:18000')
  })
})
