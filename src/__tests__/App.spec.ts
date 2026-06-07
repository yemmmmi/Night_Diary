import { mount, flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { invoke } from '@tauri-apps/api/core'
import { createRouter, createMemoryHistory } from 'vue-router'

import App from '../App.vue'
import HomeScene from '../pages/HomeScene.vue'

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}))

describe('App', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(invoke).mockImplementation((cmd: string) => {
      if (cmd === 'get_backend_port') {
        return Promise.resolve(18000)
      }
      if (cmd === 'check_backend_health') {
        return Promise.resolve(true)
      }
      return Promise.reject(new Error(`unexpected: ${cmd}`))
    })
  })

  it('shows loading then ready state', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: HomeScene }],
    })
    const wrapper = mount(App, {
      global: { plugins: [router] },
    })
    expect(wrapper.text()).toContain('正在连接 AI 引擎')

    await flushPromises()
    await router.isReady()
    expect(wrapper.text()).toContain('Night Diary V2')
    expect(wrapper.text()).toContain('http://127.0.0.1:18000')
  })
})
