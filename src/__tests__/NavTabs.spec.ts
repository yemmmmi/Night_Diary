import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

const push = vi.fn()
let routeName = 'timeline'

vi.mock('vue-router', () => ({
  useRoute: () => ({ name: routeName }),
  useRouter: () => ({ push }),
}))

import NavTabs from '@/shared/components/NavTabs.vue'

function mountNav(name = 'timeline') {
  routeName = name
  setActivePinia(createPinia())
  return mount(NavTabs, {
    global: {
      stubs: {
        RouterLink: { template: '<a><slot /></a>' },
      },
    },
  })
}

describe('NavTabs', () => {
  it('renders four paper text tabs and hides models from main nav', () => {
    const wrapper = mountNav()
    const tabs = wrapper.findAll('[role="tab"]')
    expect(tabs.map((t) => t.text())).toEqual(['记录', '规划', '洞悉', '笔谈'])
    expect(wrapper.text()).not.toContain('模型')
    expect(wrapper.text()).not.toContain('设置')
  })

  it('marks the active tab by route name', () => {
    const wrapper = mountNav('timeline')
    const active = wrapper.find('[role="tab"].is-active')
    expect(active.exists()).toBe(true)
    expect(active.text()).toBe('记录')
  })

  it('navigates to scene routes on tab click', async () => {
    const wrapper = mountNav('timeline')
    const tabs = wrapper.findAll('[role="tab"]')
    await tabs[0].trigger('click')
    expect(push).toHaveBeenCalledWith('/timeline')
    await tabs[3].trigger('click')
    expect(push).toHaveBeenCalledWith('/chat')
  })

  it('exposes gear entries for models and settings', () => {
    const wrapper = mountNav()
    const html = wrapper.html()
    expect(html).toContain('aria-label="模型"')
    expect(html).toContain('aria-label="设置"')
  })
})
